import { create } from 'zustand'
import type { WorkspaceInfo } from '@shared/ipc'

export type StageTabKind = 'welcome' | 'editor' | 'browser' | 'slides' | 'mission-control'
export type SidebarView = 'projects' | 'agents'
export type Theme = 'light' | 'dark'

export interface StageTab {
  id: string
  kind: StageTabKind
  title: string
}

interface ShellState {
  workspace: WorkspaceInfo | null
  tabs: StageTab[]
  activeTabId: string
  sidebarView: SidebarView
  sidebarOpen: boolean
  dockOpen: boolean
  theme: Theme

  setWorkspace(workspace: WorkspaceInfo | null): void
  openTab(kind: StageTabKind, title?: string): void
  closeTab(id: string): void
  activateTab(id: string): void
  setSidebarView(view: SidebarView): void
  toggleSidebar(): void
  toggleDock(): void
  setTheme(theme: Theme): void
}

const TAB_TITLES: Record<StageTabKind, string> = {
  welcome: 'Welcome',
  editor: 'Editor',
  browser: 'Browser',
  slides: 'Slides',
  'mission-control': 'Mission Control'
}

let nextTabId = 1
const makeTab = (kind: StageTabKind, title?: string): StageTab => {
  return { id: `tab-${nextTabId++}`, kind, title: title ?? TAB_TITLES[kind] }
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

  setWorkspace: (workspace) => set({ workspace }),

  openTab: (kind, title) =>
    set((state) => {
      const tab = makeTab(kind, title)
      return { tabs: [...state.tabs, tab], activeTabId: tab.id }
    }),

  closeTab: (id) =>
    set((state) => {
      const tabs = state.tabs.filter((t) => t.id !== id)
      if (tabs.length === 0) {
        const welcome = makeTab('welcome')
        return { tabs: [welcome], activeTabId: welcome.id }
      }
      const activeTabId =
        state.activeTabId === id ? tabs[Math.max(0, tabs.length - 1)].id : state.activeTabId
      return { tabs, activeTabId }
    }),

  activateTab: (id) => set({ activeTabId: id }),
  setSidebarView: (sidebarView) => set({ sidebarView, sidebarOpen: true }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  toggleDock: () => set((state) => ({ dockOpen: !state.dockOpen })),
  setTheme: (theme) => set({ theme })
}))
