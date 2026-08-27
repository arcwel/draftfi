import type { WebContents } from 'electron'
import { IpcEvents } from '@shared/ipc'
import { broadcast } from './windows'
import { createBrowserTab, getTabWebContents, navigate } from './browser'

/**
 * Agent↔browser bridge (Phase 7): agents open and drive real shell tabs.
 * The view is created here in main, then the renderer "adopts" it as a
 * normal tab (visible in the tab strip, activated on the stage) so the user
 * watches the agent work live. Control is executeJavaScript-based: click,
 * type, read, eval, wait-for, viewport emulation, and screenshots.
 */

const LOAD_TIMEOUT_MS = 20_000
const TEXT_CAP = 8_000

let nextAgentTabId = 1

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

function requireTab(tabId: string): WebContents {
  const wc = getTabWebContents(tabId)
  if (!wc) throw new Error(`no browser tab ${tabId} — open one with browser_open first`)
  return wc
}

/** Wait until the page finishes loading (or the timeout passes). */
async function waitForLoad(wc: WebContents): Promise<void> {
  const start = Date.now()
  // loadURL resolves early for some schemes; poll the loading flag instead.
  while (wc.isLoading() && Date.now() - start < LOAD_TIMEOUT_MS) await sleep(100)
  await sleep(150) // let the first paint land
}

/** JSON-quote a string for safe embedding inside injected page scripts. */
const q = (value: string): string => JSON.stringify(value)

export async function agentOpenTab(url: string): Promise<string> {
  const tabId = `agent-tab-${nextAgentTabId++}`
  createBrowserTab(tabId)
  const wc = requireTab(tabId)
  // The renderer adds the tab to its strip and activates it, which positions
  // the native view over the stage and makes it visible.
  broadcast(IpcEvents.browserAdoptTab, { tabId, url }, null)
  navigate(tabId, url)
  await waitForLoad(wc)
  return `tabId: ${tabId}\ntitle: ${wc.getTitle()}\nurl: ${wc.getURL()}`
}

export async function agentNavigate(tabId: string, url: string): Promise<string> {
  const wc = requireTab(tabId)
  if (!/^(https?|data|about|file):/i.test(url)) throw new Error(`unsupported URL scheme: ${url}`)
  navigate(tabId, url)
  await waitForLoad(wc)
  return `title: ${wc.getTitle()}\nurl: ${wc.getURL()}`
}

export async function agentReadPage(tabId: string, selector?: string): Promise<string> {
  const wc = requireTab(tabId)
  if (selector) {
    const script = `(() => {
      const el = document.querySelector(${q(selector)})
      return el ? el.innerText : null
    })()`
    const text = (await wc.executeJavaScript(script, true)) as string | null
    if (text === null) throw new Error(`no element matches ${selector}`)
    return text.slice(0, TEXT_CAP)
  }
  const script = `({ title: document.title, url: location.href, text: document.body ? document.body.innerText : '' })`
  const page = (await wc.executeJavaScript(script, true)) as {
    title: string
    url: string
    text: string
  }
  return `title: ${page.title}\nurl: ${page.url}\n\n${page.text.slice(0, TEXT_CAP)}`
}

export async function agentEval(tabId: string, expression: string): Promise<string> {
  const wc = requireTab(tabId)
  const result: unknown = await wc.executeJavaScript(expression, true)
  if (result === undefined) return 'undefined'
  try {
    return JSON.stringify(result)?.slice(0, TEXT_CAP) ?? String(result)
  } catch {
    return String(result).slice(0, TEXT_CAP)
  }
}

export async function agentClick(tabId: string, selector: string): Promise<string> {
  const wc = requireTab(tabId)
  const script = `(() => {
    const el = document.querySelector(${q(selector)})
    if (!el) return false
    el.scrollIntoView({ block: 'center' })
    el.click()
    return true
  })()`
  const found = (await wc.executeJavaScript(script, true)) as boolean
  if (!found) throw new Error(`no element matches ${selector}`)
  await sleep(100)
  return 'clicked'
}

export async function agentType(tabId: string, selector: string, text: string): Promise<string> {
  const wc = requireTab(tabId)
  // Native value setter + input/change events so framework-bound inputs
  // (React controlled components etc.) see the change.
  const script = `(() => {
    const el = document.querySelector(${q(selector)})
    if (!el) return 'missing'
    el.focus()
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      const proto = el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${q(text)})
    } else if (el.isContentEditable) {
      el.textContent = ${q(text)}
    } else {
      return 'not-editable'
    }
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
    return 'ok'
  })()`
  const result = (await wc.executeJavaScript(script, true)) as string
  if (result === 'missing') throw new Error(`no element matches ${selector}`)
  if (result === 'not-editable') throw new Error(`${selector} is not an input or editable element`)
  return 'typed'
}

export async function agentWaitFor(
  tabId: string,
  selector: string,
  timeoutMs: number
): Promise<string> {
  const wc = requireTab(tabId)
  const start = Date.now()
  const script = `!!document.querySelector(${q(selector)})`
  for (;;) {
    if ((await wc.executeJavaScript(script, true)) === true) return 'found'
    if (Date.now() - start > timeoutMs) throw new Error(`timed out waiting for ${selector}`)
    await sleep(250)
  }
}

/** Capture the page (or one element) as a PNG. Returns the raw image bytes. */
export async function agentCapture(tabId: string, selector?: string): Promise<Buffer> {
  const wc = requireTab(tabId)
  await sleep(300) // ensure the latest DOM state has painted
  if (selector) {
    const script = `(() => {
      const el = document.querySelector(${q(selector)})
      if (!el) return null
      el.scrollIntoView({ block: 'center' })
      const r = el.getBoundingClientRect()
      return { x: r.x, y: r.y, width: r.width, height: r.height }
    })()`
    const rect = (await wc.executeJavaScript(script, true)) as {
      x: number
      y: number
      width: number
      height: number
    } | null
    if (!rect) throw new Error(`no element matches ${selector}`)
    await sleep(150) // scrollIntoView may have moved the page
    const image = await wc.capturePage({
      x: Math.max(0, Math.round(rect.x)),
      y: Math.max(0, Math.round(rect.y)),
      width: Math.max(1, Math.round(rect.width)),
      height: Math.max(1, Math.round(rect.height))
    })
    return image.toPNG()
  }
  const image = await wc.capturePage()
  return image.toPNG()
}

/** Emulate a viewport size for responsiveness checks; 0×0 resets. */
export function agentSetViewport(tabId: string, width: number, height: number): string {
  const wc = requireTab(tabId)
  if (width <= 0 || height <= 0) {
    wc.disableDeviceEmulation()
    return 'viewport reset to the native stage size'
  }
  wc.enableDeviceEmulation({
    screenPosition: width < 768 ? 'mobile' : 'desktop',
    screenSize: { width, height },
    viewPosition: { x: 0, y: 0 },
    viewSize: { width, height },
    deviceScaleFactor: 0,
    scale: 1
  })
  return `viewport emulating ${width}×${height}`
}
