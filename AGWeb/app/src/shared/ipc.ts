/**
 * Typed IPC contract shared by main, preload, and renderer.
 *
 * Every channel the renderer may invoke is declared here; the preload bridge
 * and the main-process handlers both compile against these types, so the two
 * sides cannot drift. Renderers never see Node APIs — only `window.agweb`.
 */

export interface WorkspaceInfo {
  path: string
  name: string
}

export interface RecentProject {
  path: string
  name: string
  lastOpenedAt: string
}

export type ThemeSource = 'system' | 'light' | 'dark'

export interface AppInfo {
  version: string
  electron: string
  chrome: string
  platform: NodeJS.Platform
}

/** Screen-space rectangle in device-independent pixels. */
export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** Live navigation state of one embedded browser view, pushed to the renderer. */
export interface BrowserTabState {
  tabId: string
  url: string
  title: string
  isLoading: boolean
  canGoBack: boolean
  canGoForward: boolean
}

/** Channels the renderer invokes (request/response). */
export const IpcChannels = {
  appInfo: 'app:info',
  workspaceOpen: 'workspace:open',
  workspaceOpenPath: 'workspace:open-path',
  workspaceCurrent: 'workspace:current',
  workspaceRecent: 'workspace:recent',
  themeSet: 'theme:set',
  browserCreate: 'browser:create',
  browserDestroy: 'browser:destroy',
  browserNavigate: 'browser:navigate',
  browserBack: 'browser:back',
  browserForward: 'browser:forward',
  browserReload: 'browser:reload',
  browserStop: 'browser:stop',
  browserSetBounds: 'browser:set-bounds',
  browserSetVisible: 'browser:set-visible',
  browserSetCornerRadius: 'browser:set-corner-radius',
  browserDevTools: 'browser:devtools',
  deckOpen: 'deck:open',
  deckClose: 'deck:close',
  deckFocus: 'deck:focus',
  floatSync: 'float:sync',
  shellBroadcast: 'shell:broadcast'
} as const

/** Events pushed from main to the renderer. */
export const IpcEvents = {
  workspaceChanged: 'event:workspace-changed',
  browserState: 'event:browser-state',
  browserOpenTab: 'event:browser-open-tab',
  shellSync: 'event:shell-sync',
  requestSync: 'event:request-sync',
  deckWindowClosed: 'event:deck-window-closed'
} as const

/** The API surface exposed on `window.agweb` by the preload bridge. */
export interface AgwebApi {
  getAppInfo(): Promise<AppInfo>
  /** Show a folder picker and open the chosen workspace. Null if cancelled. */
  openWorkspace(): Promise<WorkspaceInfo | null>
  /** Open a known path (e.g. from the recent-projects list). */
  openWorkspacePath(path: string): Promise<WorkspaceInfo | null>
  getCurrentWorkspace(): Promise<WorkspaceInfo | null>
  getRecentProjects(): Promise<RecentProject[]>
  /** Keep Electron's nativeTheme in sync with the renderer's choice. */
  setTheme(source: ThemeSource): Promise<void>
  onWorkspaceChanged(listener: (workspace: WorkspaceInfo) => void): () => void

  /** Embedded Chromium browser views, keyed by the renderer's tab id. */
  browser: {
    create(tabId: string): Promise<void>
    destroy(tabId: string): Promise<void>
    navigate(tabId: string, url: string): Promise<void>
    back(tabId: string): Promise<void>
    forward(tabId: string): Promise<void>
    reload(tabId: string): Promise<void>
    stop(tabId: string): Promise<void>
    /** Position the view over the renderer's content area. */
    setBounds(tabId: string, rect: Rect): Promise<void>
    setVisible(tabId: string, visible: boolean): Promise<void>
    /** Round the native view's corners to match the stage frame (0 = square). */
    setCornerRadius(tabId: string, radius: number): Promise<void>
    openDevTools(tabId: string): Promise<void>
    onState(listener: (state: BrowserTabState) => void): () => void
    /** Fired when a page requests a new window (target=_blank etc.). */
    onOpenTab(listener: (url: string) => void): () => void
  }

  /** Multi-window deck: the detached IDE window, float windows, state sync. */
  windows: {
    openDeck(): Promise<void>
    closeDeck(): Promise<void>
    focusDeck(): Promise<void>
    /** Reconcile float windows to exactly these floating group ids. */
    syncFloats(groupIds: string[]): Promise<void>
    /** Mirror the deck layout slice to every other window. */
    broadcastState(state: import('./deck').DeckSyncState): Promise<void>
    onStateSync(listener: (state: import('./deck').DeckSyncState) => void): () => void
    /** Main window only: another window booted and needs the current state. */
    onRequestSync(listener: () => void): () => void
    /** The detached deck window was closed (by Dock back or the OS). */
    onDeckClosed(listener: () => void): () => void
  }
}
