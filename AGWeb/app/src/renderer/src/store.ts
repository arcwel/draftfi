import { create } from 'zustand'
import type { BrowserTabState, WorkspaceInfo } from '@shared/ipc'
import type { AgentSessionInfo } from '@shared/agents'
import type {
  BlockGroup,
  BlockInstance,
  BlockType,
  DeckMode,
  DeckPreset,
  DeckSyncState,
  DeckZone,
  DockZone,
  RailEntry
} from '@shared/deck'

export type { BlockGroup, BlockInstance, BlockType, DeckMode, DeckPreset, DeckZone, RailEntry }

export type Theme = 'light' | 'dark'

/** A browser tab in the tab strip. Page state lives in `browserStates`. */
export interface BrowserTab {
  id: string
  /** 'web' hosts a Chromium view; 'doc' renders a Document Studio view. */
  kind: 'web' | 'doc'
  title: string
  /** For tabs opened from a link: the URL to load on first mount. */
  initialUrl?: string
  /** Document Studio tabs: the workspace-relative file being rendered. */
  docPath?: string
  /** True once a WebContentsView exists for this tab (first navigation). */
  hasContent: boolean
}

/** File types the Document Studio renders as styled documents. */
export const DOC_EXTENSIONS = new Set([
  'md',
  'markdown',
  'json',
  'yaml',
  'yml',
  'toml',
  'csv',
  'tsv'
])

export function isDocFile(path: string): boolean {
  const ext = path.split('.').pop()?.toLowerCase() ?? ''
  return DOC_EXTENSIONS.has(ext)
}

/** Where a dragged block or group is dropped. */
export type DropTarget =
  | { kind: 'stack'; groupId: string }
  | { kind: 'before'; groupId: string }
  | { kind: 'zone'; zone: DeckZone }

export const BLOCK_LABELS: Record<BlockType, string> = {
  editor: 'Editor',
  files: 'Files',
  terminal: 'Terminal',
  agents: 'Agents',
  logs: 'Logs',
  search: 'Search'
}

/** Which shell window this renderer is: the browser, the detached deck, or a float. */
export function getWindowRole(): { kind: 'main' | 'deck' | 'float'; groupId?: string } {
  const hash = window.location.hash.replace(/^#/, '')
  if (hash === 'deck') return { kind: 'deck' }
  if (hash.startsWith('float:')) return { kind: 'float', groupId: hash.slice('float:'.length) }
  return { kind: 'main' }
}

/** Terminals are always numbered (Terminal 1, Terminal 2); others only from 2. */
let blockCounts: Partial<Record<BlockType, number>> = {}
let nextBlockId = 1
let nextGroupId = 1

function makeBlock(type: BlockType): BlockInstance {
  const n = (blockCounts[type] = (blockCounts[type] ?? 0) + 1)
  const numbered = type === 'terminal' || n > 1
  return {
    id: `block-${nextBlockId++}`,
    type,
    title: numbered ? `${BLOCK_LABELS[type]} ${n}` : BLOCK_LABELS[type]
  }
}

function makeGroup(zone: DeckZone, members: BlockInstance[]): BlockGroup {
  return {
    id: `group-${nextGroupId++}`,
    zone,
    blockIds: members.map((b) => b.id),
    activeBlockId: members[members.length - 1]?.id ?? ''
  }
}

let nextTabId = 1
function makeTab(initialUrl?: string): BrowserTab {
  return { id: `tab-${nextTabId++}`, kind: 'web', title: 'New Tab', initialUrl, hasContent: false }
}

function makeDocTab(docPath: string): BrowserTab {
  return {
    id: `tab-${nextTabId++}`,
    kind: 'doc',
    title: docPath.split('/').pop() ?? docPath,
    docPath,
    hasContent: false
  }
}

interface DeckLayout {
  blocks: Record<string, BlockInstance>
  groups: BlockGroup[]
  rail: RailEntry[]
}

function defaultDeck(): DeckLayout {
  const editor = makeBlock('editor')
  const files = makeBlock('files')
  const terminal = makeBlock('terminal')
  const agents = makeBlock('agents')
  return {
    blocks: {
      [editor.id]: editor,
      [files.id]: files,
      [terminal.id]: terminal,
      [agents.id]: agents
    },
    groups: [
      makeGroup('right', [editor]),
      makeGroup('right', [files]),
      makeGroup('bottom', [terminal]),
      makeGroup('bottom', [agents])
    ],
    rail: []
  }
}

/* ---- Per-project layout persistence (localStorage) ---- */

interface LayoutSnapshot extends DeckLayout {
  counters: {
    nextBlockId: number
    nextGroupId: number
    blockCounts: Partial<Record<BlockType, number>>
  }
}

const layoutKey = (workspacePath: string | null): string =>
  `agweb.layout:${workspacePath ?? 'default'}`

function loadLayout(workspacePath: string | null): DeckLayout | null {
  try {
    const raw = localStorage.getItem(layoutKey(workspacePath))
    if (!raw) return null
    const snap = JSON.parse(raw) as LayoutSnapshot
    if (!snap.groups || !snap.blocks) return null
    nextBlockId = Math.max(nextBlockId, snap.counters?.nextBlockId ?? 1)
    nextGroupId = Math.max(nextGroupId, snap.counters?.nextGroupId ?? 1)
    blockCounts = { ...blockCounts, ...snap.counters?.blockCounts }
    return { blocks: snap.blocks, groups: snap.groups, rail: snap.rail ?? [] }
  } catch {
    return null
  }
}

function saveLayout(state: {
  workspace: WorkspaceInfo | null
  blocks: Record<string, BlockInstance>
  groups: BlockGroup[]
  rail: RailEntry[]
}): void {
  try {
    const snap: LayoutSnapshot = {
      blocks: state.blocks,
      groups: state.groups,
      rail: state.rail,
      counters: { nextBlockId, nextGroupId, blockCounts }
    }
    localStorage.setItem(layoutKey(state.workspace?.path ?? null), JSON.stringify(snap))
  } catch {
    // storage unavailable — layout just won't persist
  }
}

/* ---- Group surgery helpers (pure) ---- */

/** Remove a block from whichever group holds it; dissolve emptied groups. */
function withoutBlock(groups: BlockGroup[], blockId: string): BlockGroup[] {
  return groups
    .map((g) => {
      if (!g.blockIds.includes(blockId)) return g
      const blockIds = g.blockIds.filter((id) => id !== blockId)
      const activeBlockId =
        g.activeBlockId === blockId ? (blockIds[blockIds.length - 1] ?? '') : g.activeBlockId
      return { ...g, blockIds, activeBlockId }
    })
    .filter((g) => g.blockIds.length > 0)
}

interface ShellState {
  workspace: WorkspaceInfo | null
  theme: Theme

  tabs: BrowserTab[]
  activeTabId: string
  browserStates: Record<string, BrowserTabState>

  deckRevealed: boolean
  deckMode: DeckMode
  blocks: Record<string, BlockInstance>
  groups: BlockGroup[]
  rail: RailEntry[]

  /** Open editor documents (workspace-relative paths), shared by all editors. */
  editorTabs: string[]
  activeEditorPath: string | null
  dirtyFiles: Record<string, boolean>

  /** Agent sessions, pushed from main (every window gets agentUpdate events). */
  agentSessions: Record<string, AgentSessionInfo>
  upsertAgentSession(session: AgentSessionInfo): void
  setAgentSessions(sessions: AgentSessionInfo[]): void

  setWorkspace(workspace: WorkspaceInfo | null): void
  setTheme(theme: Theme): void

  newTab(initialUrl?: string): string
  /** Open (or focus) a Document Studio tab for a workspace file. */
  openDoc(path: string): void
  closeTab(id: string): void
  activateTab(id: string): void
  markTabHasContent(id: string): void
  updateBrowserState(state: BrowserTabState): void

  toggleDeck(): void
  /** Pop the whole deck out into its own IDE window. */
  detachDeck(): void
  /** Merge the detached deck back into the browser window. */
  attachDeck(): void
  activateBlock(groupId: string, blockId: string): void
  /** Open another instance of `type` as a new tab in `groupId`. */
  addBlockToGroup(groupId: string, type: BlockType): void
  closeBlock(blockId: string): void
  /** Drag-and-drop: move one block (tab) to a target. */
  moveBlock(blockId: string, target: DropTarget): void
  /** Drag-and-drop: move a whole group (stack) to a target. */
  moveGroup(groupId: string, target: DropTarget): void
  /** Collapse a block to the rail; restore puts it back in its old zone. */
  sendToRail(blockId: string): void
  restoreFromRail(blockId: string): void
  applyPreset(preset: DeckPreset): void

  openFile(path: string, line?: number): void
  closeEditorTab(path: string): void
  setFileDirty(path: string, dirty: boolean): void
  /** Line the editor should scroll to after opening activeEditorPath. */
  pendingRevealLine: number | null
  clearPendingReveal(): void
  /** Add a fresh block of `type` to the deck as its own group. */
  addBlock(type: BlockType): void
}

const initialTab = makeTab()
const initialDeck = loadLayout(null) ?? defaultDeck()

export const useShellStore = create<ShellState>((set) => ({
  workspace: null,
  theme: 'dark',

  tabs: [initialTab],
  activeTabId: initialTab.id,
  browserStates: {},

  deckRevealed: false,
  deckMode: 'attached',
  blocks: initialDeck.blocks,
  groups: initialDeck.groups,
  rail: initialDeck.rail,
  editorTabs: [],
  activeEditorPath: null,
  dirtyFiles: {},
  agentSessions: {},

  upsertAgentSession: (session) =>
    set((state) => ({ agentSessions: { ...state.agentSessions, [session.id]: session } })),

  setAgentSessions: (sessions) =>
    set({ agentSessions: Object.fromEntries(sessions.map((s) => [s.id, s])) }),

  setWorkspace: (workspace) =>
    set((state) => {
      if (workspace?.path === state.workspace?.path) return { workspace }
      const layout = loadLayout(workspace?.path ?? null)
      return layout ? { workspace, ...layout } : { workspace }
    }),

  setTheme: (theme) => set({ theme }),

  newTab: (initialUrl) => {
    const tab = makeTab(initialUrl)
    set((state) => ({ tabs: [...state.tabs, tab], activeTabId: tab.id }))
    return tab.id
  },

  openDoc: (path) =>
    set((state) => {
      const existing = state.tabs.find((t) => t.kind === 'doc' && t.docPath === path)
      if (existing) return { activeTabId: existing.id }
      const tab = makeDocTab(path)
      return { tabs: [...state.tabs, tab], activeTabId: tab.id }
    }),

  closeTab: (id) =>
    set((state) => {
      const closing = state.tabs.find((t) => t.id === id)
      if (closing?.kind === 'web' && closing.hasContent) void window.agweb.browser.destroy(id)
      const browserStates = { ...state.browserStates }
      delete browserStates[id]

      const tabs = state.tabs.filter((t) => t.id !== id)
      if (tabs.length === 0) {
        const fresh = makeTab()
        return { tabs: [fresh], activeTabId: fresh.id, browserStates }
      }
      const activeTabId =
        state.activeTabId === id ? tabs[Math.max(0, tabs.length - 1)].id : state.activeTabId
      return { tabs, activeTabId, browserStates }
    }),

  activateTab: (id) => set({ activeTabId: id }),

  markTabHasContent: (id) =>
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === id ? { ...t, hasContent: true } : t))
    })),

  updateBrowserState: (browserState) =>
    set((state) => ({
      browserStates: { ...state.browserStates, [browserState.tabId]: browserState },
      tabs: state.tabs.map((tab) => {
        if (tab.id !== browserState.tabId) return tab
        const title = browserState.title || hostOf(browserState.url) || 'New Tab'
        return { ...tab, title, hasContent: true }
      })
    })),

  toggleDeck: () => set((state) => ({ deckRevealed: !state.deckRevealed })),

  detachDeck: () => set({ deckMode: 'detached', deckRevealed: false }),

  attachDeck: () => set({ deckMode: 'attached', deckRevealed: true }),

  activateBlock: (groupId, blockId) =>
    set((state) => ({
      groups: state.groups.map((g) => (g.id === groupId ? { ...g, activeBlockId: blockId } : g))
    })),

  addBlockToGroup: (groupId, type) =>
    set((state) => {
      const block = makeBlock(type)
      return {
        blocks: { ...state.blocks, [block.id]: block },
        groups: state.groups.map((g) =>
          g.id === groupId
            ? { ...g, blockIds: [...g.blockIds, block.id], activeBlockId: block.id }
            : g
        )
      }
    }),

  closeBlock: (blockId) =>
    set((state) => {
      if (state.blocks[blockId]?.type === 'terminal') void window.agweb.terminal.dispose(blockId)
      const blocks = { ...state.blocks }
      delete blocks[blockId]
      return {
        blocks,
        groups: withoutBlock(state.groups, blockId),
        rail: state.rail.filter((r) => r.blockId !== blockId)
      }
    }),

  moveBlock: (blockId, target) =>
    set((state) => {
      const source = state.groups.find((g) => g.blockIds.includes(blockId))
      if (!source) return {}
      if (target.kind === 'stack' && target.groupId === source.id) return {}

      let groups = withoutBlock(state.groups, blockId)
      if (target.kind === 'stack') {
        groups = groups.map((g) =>
          g.id === target.groupId
            ? { ...g, blockIds: [...g.blockIds, blockId], activeBlockId: blockId }
            : g
        )
        if (!groups.some((g) => g.blockIds.includes(blockId))) {
          groups = [
            ...groups,
            { ...makeGroup(source.zone, []), blockIds: [blockId], activeBlockId: blockId }
          ]
        }
      } else if (target.kind === 'before') {
        const index = groups.findIndex((g) => g.id === target.groupId)
        const zone = groups[index]?.zone ?? source.zone
        const fresh = { ...makeGroup(zone, []), blockIds: [blockId], activeBlockId: blockId }
        if (index < 0) groups = [...groups, fresh]
        else groups = [...groups.slice(0, index), fresh, ...groups.slice(index)]
      } else {
        if (source.blockIds.length === 1 && source.zone === target.zone) return {}
        groups = [
          ...groups,
          { ...makeGroup(target.zone, []), blockIds: [blockId], activeBlockId: blockId }
        ]
      }
      return { groups }
    }),

  moveGroup: (groupId, target) =>
    set((state) => {
      const source = state.groups.find((g) => g.id === groupId)
      if (!source) return {}
      if (target.kind === 'stack') {
        if (target.groupId === groupId) return {}
        const groups = state.groups
          .filter((g) => g.id !== groupId)
          .map((g) =>
            g.id === target.groupId
              ? {
                  ...g,
                  blockIds: [...g.blockIds, ...source.blockIds],
                  activeBlockId: source.activeBlockId
                }
              : g
          )
        return { groups }
      }
      if (target.kind === 'before') {
        if (target.groupId === groupId) return {}
        const rest = state.groups.filter((g) => g.id !== groupId)
        const index = rest.findIndex((g) => g.id === target.groupId)
        if (index < 0) return {}
        const moved = { ...source, zone: rest[index].zone }
        return { groups: [...rest.slice(0, index), moved, ...rest.slice(index)] }
      }
      if (source.zone === target.zone && target.zone !== 'floating') {
        const rest = state.groups.filter((g) => g.id !== groupId)
        return { groups: [...rest, source] }
      }
      return {
        groups: [...state.groups.filter((g) => g.id !== groupId), { ...source, zone: target.zone }]
      }
    }),

  sendToRail: (blockId) =>
    set((state) => {
      const source = state.groups.find((g) => g.blockIds.includes(blockId))
      if (!source) return {}
      const prevZone: DockZone = source.zone === 'floating' ? 'right' : source.zone
      return {
        groups: withoutBlock(state.groups, blockId),
        rail: [...state.rail, { blockId, prevZone }]
      }
    }),

  restoreFromRail: (blockId) =>
    set((state) => {
      const entry = state.rail.find((r) => r.blockId === blockId)
      if (!entry) return {}
      return {
        rail: state.rail.filter((r) => r.blockId !== blockId),
        groups: [
          ...state.groups,
          { ...makeGroup(entry.prevZone, []), blockIds: [blockId], activeBlockId: blockId }
        ]
      }
    }),

  pendingRevealLine: null,
  clearPendingReveal: () => set({ pendingRevealLine: null }),

  openFile: (path, line) =>
    set((state) => ({
      editorTabs: state.editorTabs.includes(path) ? state.editorTabs : [...state.editorTabs, path],
      activeEditorPath: path,
      pendingRevealLine: line ?? null,
      deckRevealed: state.deckMode === 'attached' ? true : state.deckRevealed
    })),

  addBlock: (type) =>
    set((state) => {
      const block = makeBlock(type)
      const zone: DeckZone = type === 'terminal' || type === 'logs' ? 'bottom' : 'right'
      return {
        blocks: { ...state.blocks, [block.id]: block },
        groups: [
          ...state.groups,
          { ...makeGroup(zone, []), blockIds: [block.id], activeBlockId: block.id }
        ],
        deckRevealed: state.deckMode === 'attached' ? true : state.deckRevealed
      }
    }),

  closeEditorTab: (path) =>
    set((state) => {
      const editorTabs = state.editorTabs.filter((p) => p !== path)
      const dirtyFiles = { ...state.dirtyFiles }
      delete dirtyFiles[path]
      const activeEditorPath =
        state.activeEditorPath === path
          ? (editorTabs[editorTabs.length - 1] ?? null)
          : state.activeEditorPath
      return { editorTabs, activeEditorPath, dirtyFiles }
    }),

  setFileDirty: (path, dirty) =>
    set((state) => ({ dirtyFiles: { ...state.dirtyFiles, [path]: dirty } })),

  applyPreset: (preset) =>
    set((state) => {
      if (preset === 'browsing') return { deckRevealed: false }

      const blocks = { ...state.blocks }
      const ofType = (type: BlockType): BlockInstance[] =>
        Object.values(blocks).filter((b) => b.type === type)
      const need = (type: BlockType): BlockInstance[] => {
        const existing = ofType(type)
        if (existing.length > 0) return existing
        const fresh = makeBlock(type)
        blocks[fresh.id] = fresh
        return [fresh]
      }

      const groups =
        preset === 'building'
          ? [
              makeGroup('right', need('editor')),
              makeGroup('right', need('files')),
              makeGroup('bottom', need('terminal')),
              makeGroup('bottom', need('agents'))
            ]
          : [
              makeGroup('right', need('editor')),
              makeGroup('right', need('files')),
              makeGroup('bottom', [...need('terminal'), ...need('logs')]),
              makeGroup('bottom', need('agents'))
            ]

      // Blocks outside the preset's types (Search, Logs under Building…)
      // must not be orphaned: keep each as its own group in a sensible zone.
      const placed = new Set(groups.flatMap((g) => g.blockIds))
      for (const block of Object.values(blocks)) {
        if (placed.has(block.id)) continue
        const zone: DeckZone =
          block.type === 'terminal' || block.type === 'logs' ? 'bottom' : 'right'
        groups.push({ ...makeGroup(zone, []), blockIds: [block.id], activeBlockId: block.id })
      }

      return { blocks, groups, rail: [], deckRevealed: true }
    })
}))

/* ---- Cross-window sync + persistence ---- */

let applyingRemote = false

/** Apply a layout slice broadcast by another shell window. */
export function applyRemoteState(state: DeckSyncState): void {
  applyingRemote = true
  try {
    useShellStore.setState(state)
  } finally {
    applyingRemote = false
  }
}

export function currentSyncState(): DeckSyncState {
  const s = useShellStore.getState()
  return {
    blocks: s.blocks,
    groups: s.groups,
    rail: s.rail,
    deckMode: s.deckMode,
    editorTabs: s.editorTabs,
    activeEditorPath: s.activeEditorPath
  }
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
// Seed with the boot state so unrelated changes (workspace, tabs, theme)
// never broadcast — a fresh window broadcasting its stale persisted layout
// would clobber the live state in every other window.
let lastSlice: DeckSyncState = currentSyncState()
useShellStore.subscribe((state) => {
  const changed =
    lastSlice.blocks !== state.blocks ||
    lastSlice.groups !== state.groups ||
    lastSlice.rail !== state.rail ||
    lastSlice.deckMode !== state.deckMode ||
    lastSlice.editorTabs !== state.editorTabs ||
    lastSlice.activeEditorPath !== state.activeEditorPath
  if (!changed) return
  lastSlice = {
    blocks: state.blocks,
    groups: state.groups,
    rail: state.rail,
    deckMode: state.deckMode,
    editorTabs: state.editorTabs,
    activeEditorPath: state.activeEditorPath
  }
  if (!applyingRemote) void window.agweb.windows.broadcastState(lastSlice)
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveLayout(useShellStore.getState()), 400)
})

function hostOf(url: string): string | null {
  try {
    return new URL(url).host || null
  } catch {
    return null
  }
}
