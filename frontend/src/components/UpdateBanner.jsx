import { useStore } from '../store/useStore'

// F1: a small "update available" pill in the header, linking to the release.
// Only shows in the packaged app when a newer version is published.
export default function UpdateBanner() {
  const info = useStore((s) => s.updateInfo)
  const dismissed = useStore((s) => s.updateDismissed)
  const dismiss = useStore((s) => s.dismissUpdate)

  if (dismissed || !info?.update_available) return null

  return (
    <div className="flex items-center gap-2 rounded-md border border-sky-700 bg-sky-950/50 px-2.5 py-1 text-[11px] text-sky-200">
      <span aria-hidden>⬆</span>
      <a
        href={info.url}
        target="_blank"
        rel="noreferrer"
        className="font-medium underline decoration-sky-500/60 underline-offset-2 hover:text-white"
      >
        {info.latest} available
      </a>
      <button
        onClick={dismiss}
        title="Dismiss"
        className="text-sky-400/70 hover:text-white"
      >
        ✕
      </button>
    </div>
  )
}
