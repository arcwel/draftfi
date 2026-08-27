import { useCallback, useEffect } from 'react'
import { Sidebar } from '@/components/Sidebar'
import { StageTabs } from '@/components/StageTabs'
import { BottomDock } from '@/components/BottomDock'
import { StatusBar } from '@/components/StatusBar'
import { useShellStore } from '@/store'
import { useThemeEffect } from '@/theme'
import { useShortcut } from '@/shortcuts'

export default function App(): React.JSX.Element {
  const { sidebarOpen, dockOpen, toggleSidebar, toggleDock, openTab, closeTab } = useShellStore()
  const setWorkspace = useShellStore((s) => s.setWorkspace)
  const setTheme = useShellStore((s) => s.setTheme)

  useThemeEffect()

  useEffect(() => {
    void window.agweb.getCurrentWorkspace().then(setWorkspace)
    return window.agweb.onWorkspaceChanged(setWorkspace)
  }, [setWorkspace])

  useShortcut(
    'mod+b',
    'Toggle sidebar',
    useCallback(() => toggleSidebar(), [toggleSidebar])
  )
  useShortcut(
    'mod+j',
    'Toggle bottom dock',
    useCallback(() => toggleDock(), [toggleDock])
  )
  useShortcut(
    'mod+t',
    'New browser tab',
    useCallback(() => openTab('browser'), [openTab])
  )
  useShortcut(
    'mod+w',
    'Close active tab',
    useCallback(() => closeTab(useShellStore.getState().activeTabId), [closeTab])
  )
  useShortcut(
    'mod+shift+l',
    'Toggle light/dark theme',
    useCallback(() => {
      setTheme(useShellStore.getState().theme === 'dark' ? 'light' : 'dark')
    }, [setTheme])
  )

  return (
    <div className="flex h-full flex-col bg-slate-50 text-slate-900 dark:bg-[#0b0f14] dark:text-slate-100">
      <div className="flex min-h-0 flex-1">
        {sidebarOpen && <Sidebar />}
        <div className="flex min-w-0 flex-1 flex-col">
          <StageTabs />
          {dockOpen && <BottomDock />}
        </div>
      </div>
      <StatusBar />
    </div>
  )
}
