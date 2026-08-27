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

  mainWindow.on('closed', () => {
    mainWindow = null
  })

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
