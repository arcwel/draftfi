import { useStore } from '../store/useStore'

// Reprocess unresolved data and refresh the whole view, with a live working
// indicator (spinning icon while in progress).
export default function SyncButton() {
  const sync = useStore((s) => s.sync)
  const syncing = useStore((s) => s.syncing)
  const result = useStore((s) => s.syncResult)

  return (
    <div className="flex items-center gap-2">
      {result && !syncing && (
        <span className="text-[11px] text-gray-400">
          {result.recategorized > 0
            ? `✓ Categorized ${result.recategorized}`
            : result.still_uncategorized > 0
              ? `${result.still_uncategorized} still uncategorized`
              : 'Up to date'}
        </span>
      )}
      <button
        onClick={sync}
        disabled={syncing}
        title="Reprocess data and refresh"
        className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition
          ${
            syncing
              ? 'border-sky-600 bg-sky-950/50 text-sky-300'
              : 'border-edge bg-panel text-gray-200 hover:border-sky-500 hover:text-sky-300'
          }`}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`}
        >
          <path d="M21 12a9 9 0 1 1-2.64-6.36" />
          <path d="M21 3v6h-6" />
        </svg>
        {syncing ? 'Syncing…' : 'Sync'}
      </button>
    </div>
  )
}
