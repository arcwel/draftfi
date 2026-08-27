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
  platform: string
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
  shellBroadcast: 'shell:broadcast',
  fsList: 'fs:list',
  fsRead: 'fs:read',
  fsWrite: 'fs:write',
  fsCreate: 'fs:create',
  fsRename: 'fs:rename',
  fsDelete: 'fs:delete',
  dialogConfirm: 'dialog:confirm',
  termCreate: 'term:create',
  termInput: 'term:input',
  termResize: 'term:resize',
  termDispose: 'term:dispose',
  termAttach: 'term:attach',
  searchQuery: 'search:query',
  exportHtml: 'export:html',
  exportPdf: 'export:pdf',
  exportCapture: 'export:capture',
  agentStart: 'agent:start',
  agentApprove: 'agent:approve',
  agentReject: 'agent:reject',
  agentStop: 'agent:stop',
  agentList: 'agent:list',
  agentKeyStatus: 'agent:key-status',
  agentSetKey: 'agent:set-key'
} as const

/** One project-search match. */
export interface SearchHit {
  path: string
  line: number
  text: string
}

/** Events pushed from main to the renderer. */
export const IpcEvents = {
  workspaceChanged: 'event:workspace-changed',
  browserState: 'event:browser-state',
  browserOpenTab: 'event:browser-open-tab',
  browserAdoptTab: 'event:browser-adopt-tab',
  shellSync: 'event:shell-sync',
  requestSync: 'event:request-sync',
  deckWindowClosed: 'event:deck-window-closed',
  fsChanged: 'event:fs-changed',
  termData: 'event:term-data',
  termExit: 'event:term-exit',
  agentUpdate: 'event:agent-update'
} as const

export interface FsEntry {
  name: string
  kind: 'file' | 'dir'
}

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
    /** An agent created a browser view in main; adopt it as a real tab. */
    onAdoptTab(listener: (tabId: string, url: string) => void): () => void
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

  /** Workspace-scoped filesystem (paths relative to the open workspace). */
  fs: {
    list(rel: string): Promise<FsEntry[]>
    read(rel: string): Promise<{ content?: string; error?: string }>
    write(rel: string, content: string): Promise<{ error?: string }>
    create(rel: string, kind: 'file' | 'dir'): Promise<{ error?: string }>
    rename(fromRel: string, toRel: string): Promise<{ error?: string }>
    remove(rel: string): Promise<{ error?: string }>
    onChanged(listener: () => void): () => void
  }

  /** Native confirm dialog (window.confirm is unavailable in Electron). */
  confirm(message: string): Promise<boolean>

  /** Project-wide text search (ripgrep when available, Node fallback). */
  search(query: string): Promise<SearchHit[]>

  /** Document Studio exports; empty result = user cancelled the dialog. */
  exports: {
    html(html: string, suggestedName: string): Promise<{ path?: string; error?: string }>
    pdf(html: string, suggestedName: string): Promise<{ path?: string; error?: string }>
    /** Capture a region of this window (the stage) as a PNG. */
    capture(rect: Rect, suggestedName: string): Promise<{ path?: string; error?: string }>
  }

  /** Claude-powered agent sessions: plan → approve → execute in the workspace. */
  agents: {
    /** Start planning a task; resolves to the new session id. */
    start(task: string): Promise<string>
    approve(id: string): Promise<void>
    reject(id: string): Promise<void>
    stop(id: string): Promise<void>
    list(): Promise<import('./agents').AgentSessionInfo[]>
    keyStatus(): Promise<import('./agents').AgentKeyStatus>
    setKey(key: string): Promise<import('./agents').AgentKeyStatus>
    /** Fired whenever any session's plan, log, or status changes. */
    onUpdate(listener: (session: import('./agents').AgentSessionInfo) => void): () => void
  }

  /** Terminal sessions, keyed by block id; they outlive renderer mounts. */
  terminal: {
    create(id: string, cols: number, rows: number): Promise<void>
    input(id: string, data: string): Promise<void>
    resize(id: string, cols: number, rows: number): Promise<void>
    dispose(id: string): Promise<void>
    attach(id: string): Promise<{ buffer: string; running: boolean }>
    onData(listener: (id: string, data: string) => void): () => void
    onExit(listener: (id: string, code: number) => void): () => void
  }
}
