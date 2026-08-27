// Launches the built app, verifies the browser-first shell + Dev Deck, and
// saves a screenshot. Usage: node scripts/smoke.mjs [screenshot.png]
// (run under xvfb on headless CI)
import { _electron as electron } from 'playwright-core'

const screenshotPath = process.argv[2] ?? 'smoke.png'

const app = await electron.launch({
  args: ['out/main/index.js', '--no-sandbox'],
  cwd: new URL('..', import.meta.url).pathname
})

try {
  const window = await app.firstWindow()

  // Browser-first default: start page, no dev UI.
  await window.waitForSelector('text=AGWeb', { timeout: 15000 })
  const title = await window.title()
  if (title !== 'AGWeb') throw new Error(`Unexpected window title: ${title}`)

  // Navigate via the address bar; the page title must round-trip
  // Chromium → main → renderer tab strip.
  const dataUrl = 'data:text/html,<title>Smoke Page</title><h1>ok</h1>'
  await window.fill('input[placeholder="Enter URL or search…"]', dataUrl)
  await window.press('input[placeholder="Enter URL or search…"]', 'Enter')
  await window.waitForSelector('text=Smoke Page', { timeout: 15000 })

  // Reveal the Dev Deck (⌘D / Ctrl+D) and verify the stage + blocks.
  await window.keyboard.press('ControlOrMeta+d')
  await window.waitForSelector('.workspace.revealed', { timeout: 5000 })
  await window.waitForSelector('text=Terminal 1')

  // Tabbed stacks + multiple instances: open a second terminal in the group.
  await window.click('button[aria-label="New terminal"]')
  await window.waitForSelector('text=Terminal 2')

  // Layout preset: Debugging stacks terminals with a fresh Logs block.
  await window.click('button:has-text("Layout")')
  await window.click('button:has-text("Debugging")')
  await window.waitForSelector('button:has-text("Logs")')

  // Drag-and-drop: drag the Logs tab onto the Agents group header to stack it.
  const agentsHeader = window
    .locator('[data-deck-header]')
    .filter({ has: window.locator('button', { hasText: 'Agents' }) })
  await window.locator('button', { hasText: 'Logs' }).first().dragTo(agentsHeader.first())
  const stacked = agentsHeader.filter({ has: window.locator('button', { hasText: 'Logs' }) })
  await stacked.first().waitFor({ timeout: 5000 })

  // Rail: collapse the stacked Logs block to the rail, then restore it.
  await window.click('button[aria-label="Send Logs to rail"]')
  await window.waitForSelector('button[aria-label="Restore Logs"]')

  await window.waitForTimeout(700) // let transitions settle
  await window.screenshot({ path: screenshotPath })

  await window.click('button[aria-label="Restore Logs"]')
  await window.waitForSelector('button:has-text("Logs")')

  // Float: pop the Files stack out as its own window, then dock it back.
  const floatPromise = app.waitForEvent('window')
  await window.click('button[aria-label="Float Files"]')
  const floatWin = await floatPromise
  await floatWin.waitForSelector('text=Files', { timeout: 15000 })
  await floatWin.click('button[aria-label="Dock back"]')
  await window
    .locator('[data-deck-header]')
    .filter({ has: window.locator('button', { hasText: 'Files' }) })
    .first()
    .waitFor({ timeout: 5000 })

  // Detach: the whole deck becomes a standalone IDE window; the browser
  // reverts to pure browsing with a "Deck detached" indicator.
  const deckPromise = app.waitForEvent('window')
  await window.click('button[aria-label="Detach deck"]')
  const deckWin = await deckPromise
  await deckWin.waitForSelector('text=Dock back', { timeout: 15000 })
  await deckWin.waitForSelector('text=Terminal 1')
  await window.waitForSelector('text=Deck detached')
  await deckWin.screenshot({ path: screenshotPath.replace(/\.png$/, '-deckwin.png') })

  // Dock back merges everything into the browser window's Stage layout.
  await deckWin.click('text=Dock back')
  await window.waitForSelector('.workspace.revealed', { timeout: 5000 })

  // Hide the deck again — back to pure browsing.
  await window.keyboard.press('ControlOrMeta+d')
  await window.waitForSelector('.workspace:not(.revealed)', { timeout: 5000 })

  console.log(`smoke OK — screenshot: ${screenshotPath}`)
} finally {
  await app.close()
}
