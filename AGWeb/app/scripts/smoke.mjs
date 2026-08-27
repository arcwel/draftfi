// Launches the built app, verifies the shell renders, and saves a screenshot.
// Usage: node scripts/smoke.mjs [screenshot.png]   (run under xvfb on headless CI)
import { _electron as electron } from 'playwright-core'

const screenshotPath = process.argv[2] ?? 'smoke.png'

const app = await electron.launch({
  args: ['out/main/index.js', '--no-sandbox'],
  cwd: new URL('..', import.meta.url).pathname
})

try {
  const window = await app.firstWindow()
  await window.waitForSelector('text=AGWeb', { timeout: 15000 })
  const title = await window.title()
  if (title !== 'AGWeb') throw new Error(`Unexpected window title: ${title}`)

  // Exercise the shell: open a tab, toggle the dock, toggle theme.
  await window.click('text=+ Browser')
  await window.waitForSelector('text=Integrated Chromium tabs land in Phase 2.')
  await window.keyboard.press('ControlOrMeta+j')
  await window.waitForSelector('text=node-pty')
  await window.keyboard.press('ControlOrMeta+Shift+l')

  await window.screenshot({ path: screenshotPath })
  console.log(`smoke OK — screenshot: ${screenshotPath}`)
} finally {
  await app.close()
}
