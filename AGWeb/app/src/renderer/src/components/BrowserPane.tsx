import { useEffect, useRef, useState } from 'react'
import { useShellStore } from '@/store'

/**
 * One integrated browser tab. The page itself renders in a main-process
 * WebContentsView layered over the content area below the toolbar; this
 * component owns the navigation chrome and keeps the view's bounds and
 * visibility in sync with the DOM.
 */

/** Turn address-bar input into a navigable URL (or a search query). */
function toNavigableUrl(input: string): string | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  if (/^(https?|data|about|file):/i.test(trimmed)) return trimmed
  if (/^[^\s]+\.[^\s/]+(\/.*)?$/.test(trimmed) || /^localhost(:\d+)?(\/.*)?$/.test(trimmed)) {
    return `https://${trimmed.replace(/^https?:\/\//, '')}`
  }
  return `https://duckduckgo.com/?q=${encodeURIComponent(trimmed)}`
}

export function BrowserPane({ tabId }: { tabId: string }): React.JSX.Element {
  const state = useShellStore((s) => s.browserStates[tabId])
  const initialUrl = useShellStore((s) => s.tabs.find((t) => t.id === tabId)?.initialUrl)
  const contentRef = useRef<HTMLDivElement>(null)
  const [urlInput, setUrlInput] = useState('')
  const [editing, setEditing] = useState(false)

  // Address bar shows the live URL until the user focuses it to type.
  const liveUrl = state?.url && state.url !== 'about:blank' ? state.url : ''
  const displayedUrl = editing ? urlInput : liveUrl

  // Create the view, keep its bounds glued to the content area, and show it
  // only while this pane is mounted (i.e. while its shell tab is active).
  useEffect(() => {
    let disposed = false
    const el = contentRef.current
    if (!el) return

    const syncBounds = (): void => {
      const rect = el.getBoundingClientRect()
      void window.agweb.browser.setBounds(tabId, {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height
      })
    }

    void window.agweb.browser.create(tabId).then(() => {
      if (disposed) return
      syncBounds()
      void window.agweb.browser.setVisible(tabId, true)
      if (initialUrl) void window.agweb.browser.navigate(tabId, initialUrl)
    })

    const observer = new ResizeObserver(syncBounds)
    observer.observe(el)
    window.addEventListener('resize', syncBounds)

    return () => {
      disposed = true
      observer.disconnect()
      window.removeEventListener('resize', syncBounds)
      void window.agweb.browser.setVisible(tabId, false)
    }
    // initialUrl is stable for the life of a tab.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabId])

  const navigate = (): void => {
    const url = toNavigableUrl(urlInput)
    if (url) void window.agweb.browser.navigate(tabId, url)
    setEditing(false)
  }

  const button =
    'rounded px-2 py-1 text-sm disabled:opacity-30 hover:bg-slate-200 dark:hover:bg-slate-700'

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-slate-200 bg-white px-2 py-1.5 dark:border-slate-800 dark:bg-[#0e1420]">
        <button
          className={button}
          disabled={!state?.canGoBack}
          onClick={() => void window.agweb.browser.back(tabId)}
          aria-label="Back"
        >
          ←
        </button>
        <button
          className={button}
          disabled={!state?.canGoForward}
          onClick={() => void window.agweb.browser.forward(tabId)}
          aria-label="Forward"
        >
          →
        </button>
        <button
          className={button}
          onClick={() =>
            state?.isLoading
              ? void window.agweb.browser.stop(tabId)
              : void window.agweb.browser.reload(tabId)
          }
          aria-label={state?.isLoading ? 'Stop' : 'Reload'}
        >
          {state?.isLoading ? '✕' : '⟳'}
        </button>
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
          className="mx-1 flex-1 rounded-md border border-slate-300 bg-slate-50 px-3 py-1 text-sm outline-none focus:border-sky-500 dark:border-slate-600 dark:bg-slate-900"
        />
        <button
          className={button}
          onClick={() => void window.agweb.browser.openDevTools(tabId)}
          title="Open DevTools"
        >
          ⚙
        </button>
      </div>
      {/* The WebContentsView is layered over this area by the main process. */}
      <div ref={contentRef} className="min-h-0 flex-1 bg-white dark:bg-[#101418]" />
    </div>
  )
}
