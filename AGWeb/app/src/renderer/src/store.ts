import { create } from 'zustand'
import type { BrowserTabState, WorkspaceInfo } from '@shared/ipc'

export type StageTabKind = 'welcome' | 'editor' | 'browser' | 'slides' | 'mission-control'
export type SidebarView = 'projects' | 'agents'
export type Theme = 'light' | 'dark'

export interface StageTab {
  id: string
  kind: StageTabKind
  title: string
  /** For browser tabs opened from a link: the URL to load on first mount. */
  initialUrl?: string
}

interface ShellState {
  workspace: WorkspaceInfo | null
  tabs: StageTab[]
  activeTabId: string
  sidebarView: SidebarView
  sidebarOpen: boolean
  dockOpen: boolean
  theme: Theme
  /** Live navigation state of embedded browser views, keyed by tab id. */
  browserStates: Record<string, BrowserTabState>

  setWorkspace(workspace: WorkspaceInfo | null): void
  openTab(kind: StageTabKind, title?: string, initialUrl?: string): string
  closeTab(id: string): void
  activateTab(id: string): void
  setSidebarView(view: SidebarView): void
  toggleSidebar(): void
  toggleDock(): void
  setTheme(theme: Theme): void
  updateBrowserState(state: BrowserTabState): void
}

const TAB_TITLES: Record<StageTabKind, string> = {
  welcome: 'Welcome',
  editor: 'Editor',
  browser: 'Browser',
  slides: 'Slides',
  'mission-control': 'Mission Control'
}

let nextTabId = 1
const makeTab = (kind: StageTabKind, title?: string, initialUrl?: string): StageTab => {
  return { id: `tab-${nextTabId++}`, kind, title: title ?? TAB_TITLES[kind], initialUrl }
}

const initialTab = makeTab('welcome')

export const useShellStore = create<ShellState>((set) => ({
  workspace: null,
  tabs: [initialTab],
  activeTabId: initialTab.id,
  sidebarView: 'projects',
  sidebarOpen: true,
  dockOpen: false,
  theme: 'dark',
  browserStates: {},

  setWorkspace: (workspace) => set({ workspace }),

  openTab: (kind, title, initialUrl) => {
    const tab = makeTab(kind, title, initialUrl)
    set((state) => ({ tabs: [...state.tabs, tab], activeTabId: tab.id }))
    return tab.id
  },

  closeTab: (id) =>
    set((state) => {
      const closing = state.tabs.find((t) => t.id === id)
      if (closing?.kind === 'browser') void window.agweb.browser.destroy(id)
      const browserStates = { ...state.browserStates }
      delete browserStates[id]

      const tabs = state.tabs.filter((t) => t.id !== id)
      if (tabs.length === 0) {
        const welcome = makeTab('welcome')
        return { tabs: [welcome], activeTabId: welcome.id, browserStates }
      }
      const activeTabId =
        state.activeTabId === id ? tabs[Math.max(0, tabs.length - 1)].id : state.activeTabId
      return { tabs, activeTabId, browserStates }
    }),

  activateTab: (id) => set({ activeTabId: id }),
  setSidebarView: (sidebarView) => set({ sidebarView, sidebarOpen: true }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  toggleDock: () => set((state) => ({ dockOpen: !state.dockOpen })),
  setTheme: (theme) => set({ theme }),

  updateBrowserState: (browserState) =>
    set((state) => ({
      browserStates: { ...state.browserStates, [browserState.tabId]: browserState },
      // Mirror the page title onto the shell tab (falling back to the URL host).
      tabs: state.tabs.map((tab) => {
        if (tab.id !== browserState.tabId) return tab
        const title = browserState.title || hostOf(browserState.url) || 'Browser'
        return { ...tab, title }
      })
    }))
}))

function hostOf(url: string): string | null {
  try {
    return new URL(url).host || null
  } catch {
    return null
  }
}
