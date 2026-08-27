import { useState } from 'react'
import { useShellStore } from '@/store'
import { BackIcon, CloseIcon, DeckIcon, ForwardIcon, ReloadIcon } from '@/components/icons'

/** Turn address-bar input into a navigable URL (or a search query). */
export function toNavigableUrl(input: string): string | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  if (/^(https?|data|about|file):/i.test(trimmed)) return trimmed
  if (/^[^\s]+\.[^\s/]+(\/.*)?$/.test(trimmed) || /^localhost(:\d+)?(\/.*)?$/.test(trimmed)) {
    return `https://${trimmed.replace(/^https?:\/\//, '')}`
  }
  return `https://duckduckgo.com/?q=${encodeURIComponent(trimmed)}`
}

/** Ensure the tab's WebContentsView exists, then load the URL into it. */
export async function navigateTab(tabId: string, url: string): Promise<void> {
  const { tabs, markTabHasContent } = useShellStore.getState()
  const tab = tabs.find((t) => t.id === tabId)
  if (tab && !tab.hasContent) {
    await window.agweb.browser.create(tabId)
    markTabHasContent(tabId)
  }
  await window.agweb.browser.navigate(tabId, url)
}

export function Toolbar(): React.JSX.Element {
  const activeTabId = useShellStore((s) => s.activeTabId)
  const state = useShellStore((s) => s.browserStates[s.activeTabId])
  const deckRevealed = useShellStore((s) => s.deckRevealed)
  const toggleDeck = useShellStore((s) => s.toggleDeck)
  const [urlInput, setUrlInput] = useState('')
  const [editing, setEditing] = useState(false)

  const liveUrl = state?.url && state.url !== 'about:blank' ? state.url : ''
  const displayedUrl = editing ? urlInput : liveUrl

  const navigate = (): void => {
    const url = toNavigableUrl(urlInput)
    if (url) void navigateTab(activeTabId, url)
    setEditing(false)
  }

  const navButton =
    'flex h-8 w-8 items-center justify-center rounded-md text-slate-500 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800'

  return (
    <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-[#0e1420]">
      <div className="flex items-center gap-0.5">
        <button
          className={navButton}
          disabled={!state?.canGoBack}
          onClick={() => void window.agweb.browser.back(activeTabId)}
          aria-label="Back"
        >
          <BackIcon />
        </button>
        <button
          className={navButton}
          disabled={!state?.canGoForward}
          onClick={() => void window.agweb.browser.forward(activeTabId)}
          aria-label="Forward"
        >
          <ForwardIcon />
        </button>
        <button
          className={navButton}
          disabled={!state}
          onClick={() =>
            state?.isLoading
              ? void window.agweb.browser.stop(activeTabId)
              : void window.agweb.browser.reload(activeTabId)
          }
          aria-label={state?.isLoading ? 'Stop' : 'Reload'}
        >
          {state?.isLoading ? <CloseIcon size={13} /> : <ReloadIcon />}
        </button>
      </div>

      <input
        value={displayedUrl}
        placeholder="Enter URL or search…"
        spellCheck={false}
        onChange={(e) => {
          setEditing(true)
          setUrlInput(e.target.value)
        }}
        onFocus={(e) => {
          setEditing(true)
          setUrlInput(liveUrl)
          e.target.select()
        }}
        onBlur={() => setEditing(false)}
        onKeyDown={(e) => e.key === 'Enter' && navigate()}
        className="mx-auto w-full max-w-2xl flex-1 rounded-lg border border-slate-300 bg-slate-50 px-3.5 py-1.5 text-[13px] outline-none focus:border-sky-500 dark:border-slate-700 dark:bg-[#0b0f14]"
      />

      <button
        onClick={toggleDeck}
        className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors duration-200 ${
          deckRevealed
            ? 'border-sky-600 bg-sky-600 text-white'
            : 'border-sky-500/40 bg-sky-500/10 text-sky-600 hover:bg-sky-500/20 dark:text-sky-400'
        }`}
        aria-label="Toggle Dev Deck"
      >
        <DeckIcon />
        <span>Deck</span>
        <span
          className={`rounded px-1.5 py-px text-[10px] font-medium ${
            deckRevealed ? 'bg-white/20' : 'bg-sky-500/15 text-sky-500 dark:text-sky-300'
          }`}
        >
          ⌘D
        </span>
      </button>
    </div>
  )
}
