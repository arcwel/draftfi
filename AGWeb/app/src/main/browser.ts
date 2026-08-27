import { BrowserWindow, WebContentsView, session } from 'electron'
import type { WebContents } from 'electron'
import { IpcEvents } from '@shared/ipc'
import type { BrowserTabState, Rect } from '@shared/ipc'

/**
 * Owns the embedded Chromium views (one WebContentsView per browser tab).
 * The renderer drives them over IPC and receives BrowserTabState pushes;
 * only the active tab's view is visible at any time.
 *
 * Pages run fully sandboxed in a dedicated persistent session with no
 * preload and no permission grants — the Phase 9 policy engine will relax
 * this per permission mode.
 */

const PARTITION = 'persist:agweb-browser'

let host: BrowserWindow | null = null
const views = new Map<string, WebContentsView>()

export function initBrowser(window: BrowserWindow): void {
  host = window
  // Default-deny web permissions (camera, mic, geolocation, notifications…).
  session.fromPartition(PARTITION).setPermissionRequestHandler((_wc, _permission, callback) => {
    callback(false)
  })
}

function sendState(tabId: string, wc: WebContents): void {
  if (!host || host.isDestroyed() || wc.isDestroyed()) return
  const state: BrowserTabState = {
    tabId,
    url: wc.getURL(),
    title: wc.getTitle(),
    isLoading: wc.isLoading(),
    canGoBack: wc.navigationHistory.canGoBack(),
    canGoForward: wc.navigationHistory.canGoForward()
  }
  host.webContents.send(IpcEvents.browserState, state)
}

export function createBrowserTab(tabId: string): void {
  if (!host || views.has(tabId)) return
  const view = new WebContentsView({
    webPreferences: {
      partition: PARTITION,
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false
    }
  })
  const wc = view.webContents

  const push = (): void => sendState(tabId, wc)
  wc.on('did-start-loading', push)
  wc.on('did-stop-loading', push)
  wc.on('did-navigate', push)
  wc.on('did-navigate-in-page', push)
  wc.on('page-title-updated', push)

  // New-window requests become new shell tabs instead of popups.
  wc.setWindowOpenHandler(({ url }) => {
    host?.webContents.send(IpcEvents.browserOpenTab, url)
    return { action: 'deny' }
  })

  view.setVisible(false)
  host.contentView.addChildView(view)
  views.set(tabId, view)
}

export function destroyBrowserTab(tabId: string): void {
  const view = views.get(tabId)
  if (!view) return
  views.delete(tabId)
  if (host && !host.isDestroyed()) host.contentView.removeChildView(view)
  if (!view.webContents.isDestroyed()) view.webContents.close()
}

export function withTab(tabId: string, fn: (view: WebContentsView) => void): void {
  const view = views.get(tabId)
  if (view && !view.webContents.isDestroyed()) fn(view)
}

/** Live webContents for a tab, or null. Used by the agent↔browser bridge. */
export function getTabWebContents(tabId: string): WebContents | null {
  const view = views.get(tabId)
  return view && !view.webContents.isDestroyed() ? view.webContents : null
}

export function navigate(tabId: string, url: string): void {
  withTab(tabId, (view) => {
    view.webContents.loadURL(url).catch(() => {
      // Load failures (bad DNS, aborted loads) surface in-page via Chromium.
    })
  })
}

export function setBounds(tabId: string, rect: Rect): void {
  withTab(tabId, (view) => {
    view.setBounds({
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    })
  })
}

export function setVisible(tabId: string, visible: boolean): void {
  withTab(tabId, (view) => view.setVisible(visible))
}

export function setCornerRadius(tabId: string, radius: number): void {
  withTab(tabId, (view) => {
    // View.setBorderRadius is not in all Electron typings yet — call defensively.
    const v = view as unknown as { setBorderRadius?: (r: number) => void }
    v.setBorderRadius?.(Math.max(0, Math.round(radius)))
  })
}

export function destroyAllBrowserTabs(): void {
  for (const tabId of [...views.keys()]) destroyBrowserTab(tabId)
}
