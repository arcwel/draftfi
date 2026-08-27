import { useEffect, useRef } from 'react'
import { useShellStore } from '@/store'
import { StartPage } from '@/components/StartPage'

/**
 * The stage hosts the active tab's page. With content, the main-process
 * WebContentsView is layered over this element — its bounds are streamed
 * here every frame of the Stage reveal animation, so the native view rides
 * the CSS transition. Without content, the start page renders in-DOM.
 */
export function Stage(): React.JSX.Element {
  const activeTabId = useShellStore((s) => s.activeTabId)
  const hasContent = useShellStore(
    (s) => s.tabs.find((t) => t.id === s.activeTabId)?.hasContent ?? false
  )
  const initialUrl = useShellStore((s) => s.tabs.find((t) => t.id === s.activeTabId)?.initialUrl)
  const deckRevealed = useShellStore((s) => s.deckRevealed)
  const ref = useRef<HTMLDivElement>(null)

  // Load link-opened tabs on first activation.
  useEffect(() => {
    if (initialUrl && !hasContent) {
      const { markTabHasContent } = useShellStore.getState()
      void window.agweb.browser.create(activeTabId).then(() => {
        markTabHasContent(activeTabId)
        void window.agweb.browser.navigate(activeTabId, initialUrl)
      })
    }
  }, [activeTabId, initialUrl, hasContent])

  // Keep the native view glued to this element and visible only while its
  // tab is active. During the deck transition the element resizes every
  // frame, so the ResizeObserver streams bounds continuously.
  useEffect(() => {
    const el = ref.current
    if (!el || !hasContent) return

    const syncBounds = (): void => {
      const rect = el.getBoundingClientRect()
      void window.agweb.browser.setBounds(activeTabId, {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height
      })
    }

    syncBounds()
    void window.agweb.browser.setVisible(activeTabId, true)

    const observer = new ResizeObserver(syncBounds)
    observer.observe(el)
    window.addEventListener('resize', syncBounds)
    el.addEventListener('transitionend', syncBounds)

    return () => {
      observer.disconnect()
      window.removeEventListener('resize', syncBounds)
      el.removeEventListener('transitionend', syncBounds)
      void window.agweb.browser.setVisible(activeTabId, false)
    }
  }, [activeTabId, hasContent])

  // Round the native view's corners to match the spotlit stage frame.
  useEffect(() => {
    if (hasContent) void window.agweb.browser.setCornerRadius(activeTabId, deckRevealed ? 10 : 0)
  }, [activeTabId, hasContent, deckRevealed])

  return (
    <div ref={ref} className="stage bg-white dark:bg-[#101418]">
      {!hasContent && <StartPage />}
    </div>
  )
}
