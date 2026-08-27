import { BrowserWindow, app, ipcMain, nativeTheme, shell } from 'electron'
import { join } from 'node:path'
import { version as appVersion } from '../../package.json'
import { IpcChannels, IpcEvents } from '@shared/ipc'
import type { AppInfo, ThemeSource } from '@shared/ipc'
import { restoreWindowState, trackWindowState } from './window-state'
import {
  getCurrentWorkspace,
  getRecentProjects,
  openWorkspaceDialog,
  openWorkspacePath
} from './workspace'
import {
  createBrowserTab,
  destroyAllBrowserTabs,
  destroyBrowserTab,
  initBrowser,
  navigate,
  setBounds,
  setCornerRadius,
  setVisible,
  withTab
} from './browser'
import type { Rect } from '@shared/ipc'

const MAX_RENDERER_RESTARTS = 3

let mainWindow: BrowserWindow | null = null
let rendererRestarts = 0

// Single-instance lock: a second launch focuses the existing window instead.
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  })
}

function createMainWindow(): void {
  const state = restoreWindowState()
  mainWindow = new BrowserWindow({
    x: state.x,
    y: state.y,
    width: state.width,
    height: state.height,
    minWidth: 900,
    minHeight: 600,
    show: false,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#0b0f14' : '#f8fafc',
    title: 'AGWeb',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  trackWindowState(mainWindow)
  if (state.isMaximized) mainWindow.maximize()

  mainWindow.once('ready-to-show', () => mainWindow?.show())

  // Crash recovery: reload a crashed renderer a bounded number of times.
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    if (details.reason === 'clean-exit' || !mainWindow) return
    console.error(`Renderer gone (${details.reason}), restarts: ${rendererRestarts}`)
    if (rendererRestarts < MAX_RENDERER_RESTARTS) {
      rendererRestarts += 1
      mainWindow.webContents.reload()
    }
  })
  mainWindow.webContents.on('did-finish-load', () => {
    rendererRestarts = 0
  })
  mainWindow.webContents.on('unresponsive', () => {
    console.warn('Renderer unresponsive')
  })

  // The shell itself never hosts external pages: open them in the OS browser
  // until the integrated browser tabs (Phase 2) land.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost')) event.preventDefault()
  })

  // Tear down browser views on 'close' (window still alive) — on 'closed' the
  // window object is destroyed and removeChildView would throw, hanging quit.
  mainWindow.on('close', () => {
    destroyAllBrowserTabs()
  })
  mainWindow.on('closed', () => {
    mainWindow = null
  })

  initBrowser(mainWindow)

  if (process.env.ELECTRON_RENDERER_URL) {
    void mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function registerIpcHandlers(): void {
  ipcMain.handle(IpcChannels.appInfo, (): AppInfo => {
    return {
      // app.getVersion() falls back to Electron's own version in unpackaged dev runs
      version: app.isPackaged ? app.getVersion() : appVersion,
      electron: process.versions.electron,
      chrome: process.versions.chrome,
      platform: process.platform
    }
  })

  ipcMain.handle(IpcChannels.workspaceOpen, async () => {
    const workspace = await openWorkspaceDialog()
    if (workspace) mainWindow?.webContents.send(IpcEvents.workspaceChanged, workspace)
    return workspace
  })

  ipcMain.handle(IpcChannels.workspaceOpenPath, (_event, path: unknown) => {
    if (typeof path !== 'string') return null
    const workspace = openWorkspacePath(path)
    if (workspace) mainWindow?.webContents.send(IpcEvents.workspaceChanged, workspace)
    return workspace
  })

  ipcMain.handle(IpcChannels.workspaceCurrent, () => getCurrentWorkspace())
  ipcMain.handle(IpcChannels.workspaceRecent, () => getRecentProjects())

  ipcMain.handle(IpcChannels.themeSet, (_event, source: unknown) => {
    if (source === 'system' || source === 'light' || source === 'dark') {
      nativeTheme.themeSource = source as ThemeSource
    }
  })

  const tabId = (value: unknown): string | null => (typeof value === 'string' ? value : null)

  ipcMain.handle(IpcChannels.browserCreate, (_e, id: unknown) => {
    const t = tabId(id)
    if (t) createBrowserTab(t)
  })
  ipcMain.handle(IpcChannels.browserDestroy, (_e, id: unknown) => {
    const t = tabId(id)
    if (t) destroyBrowserTab(t)
  })
  ipcMain.handle(IpcChannels.browserNavigate, (_e, id: unknown, url: unknown) => {
    const t = tabId(id)
    if (t && typeof url === 'string' && /^(https?|data|about|file):/i.test(url)) navigate(t, url)
  })
  ipcMain.handle(IpcChannels.browserBack, (_e, id: unknown) => {
    const t = tabId(id)
    if (t) withTab(t, (v) => v.webContents.navigationHistory.goBack())
  })
  ipcMain.handle(IpcChannels.browserForward, (_e, id: unknown) => {
    const t = tabId(id)
    if (t) withTab(t, (v) => v.webContents.navigationHistory.goForward())
  })
  ipcMain.handle(IpcChannels.browserReload, (_e, id: unknown) => {
    const t = tabId(id)
    if (t) withTab(t, (v) => v.webContents.reload())
  })
  ipcMain.handle(IpcChannels.browserStop, (_e, id: unknown) => {
    const t = tabId(id)
    if (t) withTab(t, (v) => v.webContents.stop())
  })
  ipcMain.handle(IpcChannels.browserSetBounds, (_e, id: unknown, rect: unknown) => {
    const t = tabId(id)
    const r = rect as Rect
    if (t && r && [r.x, r.y, r.width, r.height].every((n) => Number.isFinite(n))) {
      setBounds(t, r)
    }
  })
  ipcMain.handle(IpcChannels.browserSetVisible, (_e, id: unknown, visible: unknown) => {
    const t = tabId(id)
    if (t) setVisible(t, visible === true)
  })
  ipcMain.handle(IpcChannels.browserSetCornerRadius, (_e, id: unknown, radius: unknown) => {
    const t = tabId(id)
    if (t && typeof radius === 'number' && Number.isFinite(radius)) setCornerRadius(t, radius)
  })
  ipcMain.handle(IpcChannels.browserDevTools, (_e, id: unknown) => {
    const t = tabId(id)
    if (t) withTab(t, (v) => v.webContents.openDevTools({ mode: 'detach' }))
  })
}

app.whenReady().then(() => {
  registerIpcHandlers()
  createMainWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
