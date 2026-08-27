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

  await window.waitForTimeout(700) // let the reveal transition settle
  await window.screenshot({ path: screenshotPath })

  // Hide the deck again — back to pure browsing.
  await window.keyboard.press('ControlOrMeta+d')
  await window.waitForSelector('.workspace:not(.revealed)', { timeout: 5000 })

  console.log(`smoke OK — screenshot: ${screenshotPath}`)
} finally {
  await app.close()
}
