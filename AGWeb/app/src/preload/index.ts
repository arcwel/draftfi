import { contextBridge, ipcRenderer } from 'electron'
import { IpcChannels, IpcEvents } from '@shared/ipc'
import type { AgwebApi, BrowserTabState, WorkspaceInfo } from '@shared/ipc'
import type { DeckSyncState } from '@shared/deck'
import type { AgentSessionInfo } from '@shared/agents'

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
    },
    onAdoptTab: (listener) => {
      const handler = (_event: unknown, payload: { tabId: string; url: string }): void =>
        listener(payload.tabId, payload.url)
      ipcRenderer.on(IpcEvents.browserAdoptTab, handler)
      return () => ipcRenderer.removeListener(IpcEvents.browserAdoptTab, handler)
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
  },
  fs: {
    list: (rel) => ipcRenderer.invoke(IpcChannels.fsList, rel),
    read: (rel) => ipcRenderer.invoke(IpcChannels.fsRead, rel),
    write: (rel, content) => ipcRenderer.invoke(IpcChannels.fsWrite, rel, content),
    create: (rel, kind) => ipcRenderer.invoke(IpcChannels.fsCreate, rel, kind),
    rename: (fromRel, toRel) => ipcRenderer.invoke(IpcChannels.fsRename, fromRel, toRel),
    remove: (rel) => ipcRenderer.invoke(IpcChannels.fsDelete, rel),
    onChanged: (listener) => {
      const handler = (): void => listener()
      ipcRenderer.on(IpcEvents.fsChanged, handler)
      return () => ipcRenderer.removeListener(IpcEvents.fsChanged, handler)
    }
  },
  confirm: (message) => ipcRenderer.invoke(IpcChannels.dialogConfirm, message),
  search: (query) => ipcRenderer.invoke(IpcChannels.searchQuery, query),
  exports: {
    html: (html, name) => ipcRenderer.invoke(IpcChannels.exportHtml, html, name),
    pdf: (html, name) => ipcRenderer.invoke(IpcChannels.exportPdf, html, name),
    capture: (rect, name) => ipcRenderer.invoke(IpcChannels.exportCapture, rect, name)
  },
  agents: {
    start: (task) => ipcRenderer.invoke(IpcChannels.agentStart, task),
    approve: (id) => ipcRenderer.invoke(IpcChannels.agentApprove, id),
    reject: (id) => ipcRenderer.invoke(IpcChannels.agentReject, id),
    stop: (id) => ipcRenderer.invoke(IpcChannels.agentStop, id),
    list: () => ipcRenderer.invoke(IpcChannels.agentList),
    keyStatus: () => ipcRenderer.invoke(IpcChannels.agentKeyStatus),
    setKey: (key) => ipcRenderer.invoke(IpcChannels.agentSetKey, key),
    openReport: (id) => ipcRenderer.invoke(IpcChannels.agentOpenReport, id),
    clearFinished: () => ipcRenderer.invoke(IpcChannels.agentClearFinished),
    onUpdate: (listener) => {
      const handler = (_event: unknown, session: AgentSessionInfo): void => listener(session)
      ipcRenderer.on(IpcEvents.agentUpdate, handler)
      return () => ipcRenderer.removeListener(IpcEvents.agentUpdate, handler)
    },
    onReset: (listener) => {
      const handler = (_event: unknown, sessions: AgentSessionInfo[]): void => listener(sessions)
      ipcRenderer.on(IpcEvents.agentSessionsReset, handler)
      return () => ipcRenderer.removeListener(IpcEvents.agentSessionsReset, handler)
    }
  },
  terminal: {
    create: (id, cols, rows) => ipcRenderer.invoke(IpcChannels.termCreate, id, cols, rows),
    input: (id, data) => ipcRenderer.invoke(IpcChannels.termInput, id, data),
    resize: (id, cols, rows) => ipcRenderer.invoke(IpcChannels.termResize, id, cols, rows),
    dispose: (id) => ipcRenderer.invoke(IpcChannels.termDispose, id),
    attach: (id) => ipcRenderer.invoke(IpcChannels.termAttach, id),
    onData: (listener) => {
      const handler = (_e: unknown, payload: { id: string; data: string }): void =>
        listener(payload.id, payload.data)
      ipcRenderer.on(IpcEvents.termData, handler)
      return () => ipcRenderer.removeListener(IpcEvents.termData, handler)
    },
    onExit: (listener) => {
      const handler = (_e: unknown, payload: { id: string; code: number }): void =>
        listener(payload.id, payload.code)
      ipcRenderer.on(IpcEvents.termExit, handler)
      return () => ipcRenderer.removeListener(IpcEvents.termExit, handler)
    }
  }
}

contextBridge.exposeInMainWorld('agweb', api)
