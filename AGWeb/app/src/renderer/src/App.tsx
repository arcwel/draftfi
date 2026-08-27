import { useCallback, useEffect } from 'react'
import { TabStrip } from '@/components/TabStrip'
import { Toolbar } from '@/components/Toolbar'
import { Stage } from '@/components/Stage'
import { Deck } from '@/components/Deck'
import { useShellStore } from '@/store'
import { useThemeEffect } from '@/theme'
import { useShortcut } from '@/shortcuts'

export default function App(): React.JSX.Element {
  const deckRevealed = useShellStore((s) => s.deckRevealed)
  const hasRail = useShellStore((s) => s.rail.length > 0)
  const { toggleDeck, newTab, closeTab } = useShellStore()
  const setWorkspace = useShellStore((s) => s.setWorkspace)
  const setTheme = useShellStore((s) => s.setTheme)

  useThemeEffect()

  useEffect(() => {
    void window.agweb.getCurrentWorkspace().then(setWorkspace)
    return window.agweb.onWorkspaceChanged(setWorkspace)
  }, [setWorkspace])

  // Route embedded-browser events into the store: live navigation state, and
  // pages requesting a new window become new browser tabs.
  useEffect(() => {
    const offState = window.agweb.browser.onState(useShellStore.getState().updateBrowserState)
    const offOpen = window.agweb.browser.onOpenTab((url) => {
      useShellStore.getState().newTab(url)
    })
    return () => {
      offState()
      offOpen()
    }
  }, [])

  useShortcut(
    'mod+d',
    'Reveal / hide the Dev Deck',
    useCallback(() => toggleDeck(), [toggleDeck])
  )
  useShortcut(
    'mod+t',
    'New browser tab',
    useCallback(() => newTab(), [newTab])
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
    <div className="flex h-full flex-col bg-slate-100 text-slate-900 dark:bg-[#0b0f14] dark:text-slate-100">
      <TabStrip />
      <Toolbar />
      <div className={`workspace ${deckRevealed ? 'revealed' : ''} ${hasRail ? 'has-rail' : ''}`}>
        <Stage />
        <Deck />
      </div>
    </div>
  )
}
