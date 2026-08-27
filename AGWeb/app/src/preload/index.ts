import { contextBridge, ipcRenderer } from 'electron'
import { IpcChannels, IpcEvents } from '@shared/ipc'
import type { AgwebApi, BrowserTabState, WorkspaceInfo } from '@shared/ipc'
import type { DeckSyncState } from '@shared/deck'

/**
 * The only bridge between the sandboxed renderer and the main process.
 * Exposes the typed AgwebApi surface — nothing else from Node or Electron.
 */
const api: AgwebApi = {
  getAppInfo: () => ipcRenderer.invoke(IpcChannels.appInfo),
  openWorkspace: () => ipcRenderer.invoke(IpcChannels.workspaceOpen),
  openWorkspacePath: (path) => ipcRenderer.invoke(IpcChannels.workspaceOpenPath, path),
  getCurrentWorkspace: () => ipcRenderer.invoke(IpcChannels.workspaceCurrent),
  getRecentProjects: () => ipcRenderer.invoke(IpcChannels.workspaceRecent),
  setTheme: (source) => ipcRenderer.invoke(IpcChannels.themeSet, source),
  onWorkspaceChanged: (listener) => {
    const handler = (_event: unknown, workspace: WorkspaceInfo): void => listener(workspace)
    ipcRenderer.on(IpcEvents.workspaceChanged, handler)
    return () => ipcRenderer.removeListener(IpcEvents.workspaceChanged, handler)
  },
  browser: {
    create: (tabId) => ipcRenderer.invoke(IpcChannels.browserCreate, tabId),
    destroy: (tabId) => ipcRenderer.invoke(IpcChannels.browserDestroy, tabId),
    navigate: (tabId, url) => ipcRenderer.invoke(IpcChannels.browserNavigate, tabId, url),
    back: (tabId) => ipcRenderer.invoke(IpcChannels.browserBack, tabId),
    forward: (tabId) => ipcRenderer.invoke(IpcChannels.browserForward, tabId),
    reload: (tabId) => ipcRenderer.invoke(IpcChannels.browserReload, tabId),
    stop: (tabId) => ipcRenderer.invoke(IpcChannels.browserStop, tabId),
    setBounds: (tabId, rect) => ipcRenderer.invoke(IpcChannels.browserSetBounds, tabId, rect),
    setVisible: (tabId, visible) =>
      ipcRenderer.invoke(IpcChannels.browserSetVisible, tabId, visible),
    setCornerRadius: (tabId, radius) =>
      ipcRenderer.invoke(IpcChannels.browserSetCornerRadius, tabId, radius),
    openDevTools: (tabId) => ipcRenderer.invoke(IpcChannels.browserDevTools, tabId),
    onState: (listener) => {
      const handler = (_event: unknown, state: BrowserTabState): void => listener(state)
      ipcRenderer.on(IpcEvents.browserState, handler)
      return () => ipcRenderer.removeListener(IpcEvents.browserState, handler)
    },
    onOpenTab: (listener) => {
      const handler = (_event: unknown, url: string): void => listener(url)
      ipcRenderer.on(IpcEvents.browserOpenTab, handler)
      return () => ipcRenderer.removeListener(IpcEvents.browserOpenTab, handler)
    }
  },
  windows: {
    openDeck: () => ipcRenderer.invoke(IpcChannels.deckOpen),
    closeDeck: () => ipcRenderer.invoke(IpcChannels.deckClose),
    focusDeck: () => ipcRenderer.invoke(IpcChannels.deckFocus),
    syncFloats: (groupIds) => ipcRenderer.invoke(IpcChannels.floatSync, groupIds),
    broadcastState: (state) => ipcRenderer.invoke(IpcChannels.shellBroadcast, state),
    onStateSync: (listener) => {
      const handler = (_event: unknown, state: DeckSyncState): void => listener(state)
      ipcRenderer.on(IpcEvents.shellSync, handler)
      return () => ipcRenderer.removeListener(IpcEvents.shellSync, handler)
    },
    onRequestSync: (listener) => {
      const handler = (): void => listener()
      ipcRenderer.on(IpcEvents.requestSync, handler)
      return () => ipcRenderer.removeListener(IpcEvents.requestSync, handler)
    },
    onDeckClosed: (listener) => {
      const handler = (): void => listener()
      ipcRenderer.on(IpcEvents.deckWindowClosed, handler)
      return () => ipcRenderer.removeListener(IpcEvents.deckWindowClosed, handler)
    }
  }
}

contextBridge.exposeInMainWorld('agweb', api)
