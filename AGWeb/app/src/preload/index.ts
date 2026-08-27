import { contextBridge, ipcRenderer } from 'electron'
import { IpcChannels, IpcEvents } from '@shared/ipc'
import type { AgwebApi, WorkspaceInfo } from '@shared/ipc'

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
  }
}

contextBridge.exposeInMainWorld('agweb', api)
