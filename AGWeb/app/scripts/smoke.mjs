// Launches the built app against a throwaway workspace and drives the whole
// shell: browser, Deck reveal, Files→Editor→save-to-disk, live terminal,
// presets, drag-to-stack, rail, float window, detached deck window.
// Usage: node scripts/smoke.mjs [screenshot.png]   (run under xvfb on CI)
import { _electron as electron } from 'playwright-core'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const screenshotPath = process.argv[2] ?? 'smoke.png'

// Throwaway workspace + user data so runs are deterministic and never touch
// real projects or accumulated layout state.
const workspace = mkdtempSync(join(tmpdir(), 'agweb-ws-'))
writeFileSync(join(workspace, 'hello.md'), 'hello agweb\n')
mkdirSync(join(workspace, 'src'))
writeFileSync(join(workspace, 'src', 'index.ts'), 'export const answer = 42\n')

const app = await electron.launch({
  args: ['out/main/index.js', '--no-sandbox'],
  cwd: new URL('..', import.meta.url).pathname,
  env: {
    ...process.env,
    AGWEB_WORKSPACE: workspace,
    AGWEB_USER_DATA: mkdtempSync(join(tmpdir(), 'agweb-data-'))
  }
})

try {
  const window = await app.firstWindow()

  // Browser-first default: start page, then navigate via the address bar and
  // verify the page title round-trips Chromium → main → tab strip.
  await window.waitForSelector('text=AGWeb', { timeout: 15000 })
  const dataUrl = 'data:text/html,<title>Smoke Page</title><h1>ok</h1>'
  await window.fill('input[placeholder="Enter URL or search…"]', dataUrl)
  await window.press('input[placeholder="Enter URL or search…"]', 'Enter')
  await window.waitForSelector('text=Smoke Page', { timeout: 15000 })

  // Reveal the Dev Deck.
  await window.keyboard.press('ControlOrMeta+d')
  await window.waitForSelector('.workspace.revealed', { timeout: 5000 })

  // Files tree → editor: open a file, verify content, edit, save, check disk.
  await window.waitForSelector('text=hello.md', { timeout: 10000 })
  await window.click('text=hello.md')
  await window.waitForSelector('.monaco-editor', { timeout: 15000 })
  await window.waitForSelector('text=hello agweb', { timeout: 15000 })
  await window.click('.monaco-editor .view-lines')
  await window.keyboard.press('ControlOrMeta+End')
  await window.keyboard.type('smoke-edit')
  await window.keyboard.press('ControlOrMeta+s')
  await waitFor(
    () => readFileSync(join(workspace, 'hello.md'), 'utf8').includes('smoke-edit'),
    10000,
    'file save did not reach disk'
  )

  // Terminal: run a real command through the pty and see its output.
  await window.waitForSelector('.xterm', { timeout: 15000 })
  await window.click('.xterm')
  await window.keyboard.type('echo smoke-$((40+2))')
  await window.keyboard.press('Enter')
  await window.waitForSelector('text=smoke-42', { timeout: 15000 })

  await window.waitForTimeout(400)
  await window.screenshot({ path: screenshotPath })

  // Layout preset: Debugging stacks terminals with a fresh Logs block.
  await window.click('button:has-text("Layout")')
  await window.click('button:has-text("Debugging")')
  await window.waitForSelector('button:has-text("Logs")')

  // Drag-and-drop: stack the Logs tab onto the Agents group header.
  const agentsHeader = window
    .locator('[data-deck-header]')
    .filter({ has: window.locator('button', { hasText: 'Agents' }) })
  await window.locator('button', { hasText: 'Logs' }).first().dragTo(agentsHeader.first())
  await agentsHeader
    .filter({ has: window.locator('button', { hasText: 'Logs' }) })
    .first()
    .waitFor({ timeout: 5000 })

  // Rail: collapse the stacked Logs block, then restore it.
  await window.click('button[aria-label="Send Logs to rail"]')
  await window.waitForSelector('button[aria-label="Restore Logs"]')
  await window.click('button[aria-label="Restore Logs"]')
  await window.waitForSelector('button:has-text("Logs")')

  // Float: pop the Files stack out as its own window, then dock it back.
  const floatPromise = app.waitForEvent('window')
  await window.click('button[aria-label="Float Files"]')
  const floatWin = await floatPromise
  await floatWin.waitForSelector('text=hello.md', { timeout: 15000 })
  await floatWin.click('button[aria-label="Dock back"]')
  await window
    .locator('[data-deck-header]')
    .filter({ has: window.locator('button', { hasText: 'Files' }) })
    .first()
    .waitFor({ timeout: 5000 })

  // Detach: the whole deck becomes a standalone IDE window.
  const deckPromise = app.waitForEvent('window')
  await window.click('button[aria-label="Detach deck"]')
  const deckWin = await deckPromise
  await deckWin.waitForSelector('text=Dock back', { timeout: 15000 })
  await deckWin.waitForSelector('text=Terminal 1')
  await window.waitForSelector('text=Deck detached')
  await deckWin.screenshot({ path: screenshotPath.replace(/\.png$/, '-deckwin.png') })
  await deckWin.click('text=Dock back')
  await window.waitForSelector('.workspace.revealed', { timeout: 5000 })

  console.log(`smoke OK — screenshot: ${screenshotPath}`)
} finally {
  await app.close()
}

async function waitFor(check, timeoutMs, message) {
  const start = Date.now()
  for (;;) {
    try {
      if (check()) return
    } catch {
      // e.g. file not present yet
    }
    if (Date.now() - start > timeoutMs) throw new Error(message)
    await new Promise((resolve) => setTimeout(resolve, 200))
  }
}
