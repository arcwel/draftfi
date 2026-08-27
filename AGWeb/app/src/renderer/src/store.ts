import { create } from 'zustand'
import type { BrowserTabState, WorkspaceInfo } from '@shared/ipc'

export type Theme = 'light' | 'dark'

/** A browser tab in the tab strip. Page state lives in `browserStates`. */
export interface BrowserTab {
  id: string
  title: string
  /** For tabs opened from a link: the URL to load on first mount. */
  initialUrl?: string
  /** True once a WebContentsView exists for this tab (first navigation). */
  hasContent: boolean
}

export type BlockType = 'editor' | 'files' | 'terminal' | 'agents' | 'logs'
export type DeckZone = 'right' | 'bottom'

/** One instance of a dev feature. Blocks are peers: any type can have many. */
export interface BlockInstance {
  id: string
  type: BlockType
  title: string
}

/** A tabbed stack of blocks docked in a zone. One block is the active tab. */
export interface BlockGroup {
  id: string
  zone: DeckZone
  blockIds: string[]
  activeBlockId: string
}

export const BLOCK_LABELS: Record<BlockType, string> = {
  editor: 'Editor',
  files: 'Files',
  terminal: 'Terminal',
  agents: 'Agents',
  logs: 'Logs'
}

/** Terminals are always numbered (Terminal 1, Terminal 2); others only from 2. */
const blockCounts: Partial<Record<BlockType, number>> = {}
let nextBlockId = 1
function makeBlock(type: BlockType): BlockInstance {
  const n = (blockCounts[type] = (blockCounts[type] ?? 0) + 1)
  const numbered = type === 'terminal' || n > 1
  return {
    id: `block-${nextBlockId++}`,
    type,
    title: numbered ? `${BLOCK_LABELS[type]} ${n}` : BLOCK_LABELS[type]
  }
}

let nextTabId = 1
function makeTab(initialUrl?: string): BrowserTab {
  return { id: `tab-${nextTabId++}`, title: 'New Tab', initialUrl, hasContent: false }
}

let nextGroupId = 1
function makeGroup(zone: DeckZone, block: BlockInstance): BlockGroup {
  return { id: `group-${nextGroupId++}`, zone, blockIds: [block.id], activeBlockId: block.id }
}

function defaultDeck(): { blocks: Record<string, BlockInstance>; groups: BlockGroup[] } {
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
      makeGroup('right', editor),
      makeGroup('right', files),
      makeGroup('bottom', terminal),
      makeGroup('bottom', agents)
    ]
  }
}

interface ShellState {
  workspace: WorkspaceInfo | null
  theme: Theme

  tabs: BrowserTab[]
  activeTabId: string
  browserStates: Record<string, BrowserTabState>

  deckRevealed: boolean
  blocks: Record<string, BlockInstance>
  groups: BlockGroup[]

  setWorkspace(workspace: WorkspaceInfo | null): void
  setTheme(theme: Theme): void

  newTab(initialUrl?: string): string
  closeTab(id: string): void
  activateTab(id: string): void
  markTabHasContent(id: string): void
  updateBrowserState(state: BrowserTabState): void

  toggleDeck(): void
  activateBlock(groupId: string, blockId: string): void
  /** Open another instance of `type` as a new tab in `groupId`. */
  addBlockToGroup(groupId: string, type: BlockType): void
  closeBlock(blockId: string): void
}

const initialTab = makeTab()
const initialDeck = defaultDeck()

export const useShellStore = create<ShellState>((set) => ({
  workspace: null,
  theme: 'dark',

  tabs: [initialTab],
  activeTabId: initialTab.id,
  browserStates: {},

  deckRevealed: false,
  blocks: initialDeck.blocks,
  groups: initialDeck.groups,

  setWorkspace: (workspace) => set({ workspace }),
  setTheme: (theme) => set({ theme }),

  newTab: (initialUrl) => {
    const tab = makeTab(initialUrl)
    set((state) => ({ tabs: [...state.tabs, tab], activeTabId: tab.id }))
    return tab.id
  },

  closeTab: (id) =>
    set((state) => {
      const closing = state.tabs.find((t) => t.id === id)
      if (closing?.hasContent) void window.agweb.browser.destroy(id)
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
      const blocks = { ...state.blocks }
      delete blocks[blockId]
      const groups = state.groups
        .map((g) => {
          if (!g.blockIds.includes(blockId)) return g
          const blockIds = g.blockIds.filter((id) => id !== blockId)
          const activeBlockId =
            g.activeBlockId === blockId ? (blockIds[blockIds.length - 1] ?? '') : g.activeBlockId
          return { ...g, blockIds, activeBlockId }
        })
        .filter((g) => g.blockIds.length > 0)
      return { blocks, groups }
    })
}))

function hostOf(url: string): string | null {
  try {
    return new URL(url).host || null
  } catch {
    return null
  }
}
