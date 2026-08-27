import { BrowserWindow, app, dialog, ipcMain, nativeTheme, shell } from 'electron'
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
import {
  broadcast,
  closeAllChildWindows,
  closeDeckWindow,
  focusDeckWindow,
  initWindows,
  openDeckWindow,
  syncFloatWindows
} from './windows'
import {
  createEntry,
  deleteEntry,
  listDir,
  readFile,
  renameEntry,
  watchWorkspace,
  writeFile
} from './fs'
import {
  attachTerminal,
  createTerminal,
  disposeAllTerminals,
  disposeTerminal,
  resizeTerminal,
  writeTerminal
} from './terminal'
import { searchWorkspace } from './search'
import { exportCapture, exportHtml, exportPdf } from './export'
import type { WorkspaceInfo } from '@shared/ipc'

// Test/dev hooks: isolate state and open a workspace without the dialog.
if (process.env.AGWEB_USER_DATA) app.setPath('userData', process.env.AGWEB_USER_DATA)

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
    closeAllChildWindows()
  })
  mainWindow.on('closed', () => {
    mainWindow = null
  })

  initBrowser(mainWindow)
  initWindows(mainWindow)

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

  const applyWorkspace = (workspace: WorkspaceInfo | null): void => {
    if (!workspace) return
    watchWorkspace(workspace.path)
    broadcast(IpcEvents.workspaceChanged, workspace, null)
  }

  ipcMain.handle(IpcChannels.workspaceOpen, async () => {
    const workspace = await openWorkspaceDialog()
    applyWorkspace(workspace)
    return workspace
  })

  ipcMain.handle(IpcChannels.workspaceOpenPath, (_event, path: unknown) => {
    if (typeof path !== 'string') return null
    const workspace = openWorkspacePath(path)
    applyWorkspace(workspace)
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

  ipcMain.handle(IpcChannels.deckOpen, () => openDeckWindow())
  ipcMain.handle(IpcChannels.deckClose, () => closeDeckWindow())
  ipcMain.handle(IpcChannels.deckFocus, () => focusDeckWindow())
  ipcMain.handle(IpcChannels.floatSync, (_e, ids: unknown) => {
    if (Array.isArray(ids) && ids.every((id) => typeof id === 'string')) {
      syncFloatWindows(ids as string[])
    }
  })
  ipcMain.handle(IpcChannels.shellBroadcast, (event, payload: unknown) => {
    broadcast(IpcEvents.shellSync, payload, event.sender.id)
  })

  const str = (v: unknown): string | null => (typeof v === 'string' ? v : null)

  ipcMain.handle(IpcChannels.fsList, (_e, rel: unknown) => listDir(str(rel) ?? ''))
  ipcMain.handle(IpcChannels.fsRead, (_e, rel: unknown) => readFile(str(rel) ?? ''))
  ipcMain.handle(IpcChannels.fsWrite, (_e, rel: unknown, content: unknown) => {
    const r = str(rel)
    if (r === null || typeof content !== 'string') return { error: 'bad arguments' }
    return writeFile(r, content)
  })
  ipcMain.handle(IpcChannels.fsCreate, (_e, rel: unknown, kind: unknown) => {
    const r = str(rel)
    if (r === null || (kind !== 'file' && kind !== 'dir')) return { error: 'bad arguments' }
    return createEntry(r, kind)
  })
  ipcMain.handle(IpcChannels.fsRename, (_e, from: unknown, to: unknown) => {
    const f = str(from)
    const t = str(to)
    if (f === null || t === null) return { error: 'bad arguments' }
    return renameEntry(f, t)
  })
  ipcMain.handle(IpcChannels.fsDelete, (_e, rel: unknown) => {
    const r = str(rel)
    if (r === null) return { error: 'bad arguments' }
    return deleteEntry(r)
  })

  ipcMain.handle(IpcChannels.dialogConfirm, async (_e, message: unknown) => {
    if (!mainWindow) return false
    const { response } = await dialog.showMessageBox(mainWindow, {
      type: 'warning',
      buttons: ['Cancel', 'OK'],
      defaultId: 1,
      cancelId: 0,
      message: str(message) ?? 'Are you sure?'
    })
    return response === 1
  })

  const num = (v: unknown, fallback: number): number =>
    typeof v === 'number' && Number.isFinite(v) ? Math.round(v) : fallback

  ipcMain.handle(IpcChannels.termCreate, (_e, id: unknown, cols: unknown, rows: unknown) => {
    const t = str(id)
    if (t) createTerminal(t, num(cols, 80), num(rows, 24))
  })
  ipcMain.handle(IpcChannels.termInput, (_e, id: unknown, data: unknown) => {
    const t = str(id)
    if (t && typeof data === 'string') writeTerminal(t, data)
  })
  ipcMain.handle(IpcChannels.termResize, (_e, id: unknown, cols: unknown, rows: unknown) => {
    const t = str(id)
    if (t) resizeTerminal(t, num(cols, 80), num(rows, 24))
  })
  ipcMain.handle(IpcChannels.termDispose, (_e, id: unknown) => {
    const t = str(id)
    if (t) disposeTerminal(t)
  })
  ipcMain.handle(IpcChannels.termAttach, (_e, id: unknown) => {
    const t = str(id)
    return t ? attachTerminal(t) : { buffer: '', running: false }
  })

  ipcMain.handle(IpcChannels.searchQuery, (_e, query: unknown) => {
    const q = str(query)
    return q ? searchWorkspace(q) : []
  })

  const owner = (event: Electron.IpcMainInvokeEvent): BrowserWindow | null =>
    BrowserWindow.fromWebContents(event.sender)

  ipcMain.handle(IpcChannels.exportHtml, (event, html: unknown, name: unknown) => {
    const h = str(html)
    if (h === null) return { error: 'bad arguments' }
    return exportHtml(owner(event), h, str(name) ?? 'document.html')
  })
  ipcMain.handle(IpcChannels.exportPdf, (event, html: unknown, name: unknown) => {
    const h = str(html)
    if (h === null) return { error: 'bad arguments' }
    return exportPdf(owner(event), h, str(name) ?? 'document.pdf')
  })
  ipcMain.handle(IpcChannels.exportCapture, (event, rect: unknown, name: unknown) => {
    const r = rect as Rect
    if (!r || ![r.x, r.y, r.width, r.height].every((n) => Number.isFinite(n))) {
      return { error: 'bad arguments' }
    }
    return exportCapture(owner(event), r, str(name) ?? 'document.png')
  })
}

app.whenReady().then(() => {
  registerIpcHandlers()

  if (process.env.AGWEB_WORKSPACE) {
    const workspace = openWorkspacePath(process.env.AGWEB_WORKSPACE)
    if (workspace) watchWorkspace(workspace.path)
  }

  createMainWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow()
  })
})

app.on('window-all-closed', () => {
  disposeAllTerminals()
  if (process.platform !== 'darwin') app.quit()
})
