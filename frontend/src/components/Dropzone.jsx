import { useRef, useState } from 'react'
import { useStore } from '../store/useStore'

// CSV drag-and-drop with an inline processing indicator. Imports are additive:
// rows already in the database are left untouched, only new rows are added.
export default function Dropzone() {
  const importCsv = useStore((s) => s.importCsv)
  const importing = useStore((s) => s.importing)
  const summary = useStore((s) => s.importSummary)
  const resetAll = useStore((s) => s.resetAll)
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState(null)
  const [account, setAccount] = useState('')

  async function handleReset() {
    const ok = window.confirm(
      'Reset all data?\n\nThis deletes every transaction, sandbox branch, and ' +
        'budget target, and clears your plan back to $0. Your categories and ' +
        'LLM settings are kept. This cannot be undone.',
    )
    if (!ok) return
    try {
      await resetAll()
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleFile(file) {
    if (!file) return
    setError(null)
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please drop a .csv bank statement.')
      return
    }
    try {
      // Pass a stable account label (never the filename) so re-imports dedupe.
      await importCsv(file, account)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFile(e.dataTransfer.files?.[0])
        }}
        className={`rounded-lg border-2 border-dashed p-4 text-center cursor-pointer transition
          ${dragging ? 'border-sky-400 bg-sky-950/40' : 'border-edge bg-panel hover:border-gray-500'}`}
      >
        {importing ? (
          <div className="flex items-center justify-center gap-2 text-sm text-sky-300">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
            Processing statement…
          </div>
        ) : (
          <div className="text-xs text-gray-400">
            <div className="text-2xl leading-none">⤓</div>
            <div className="mt-1 font-medium text-gray-200">
              Drop bank CSV here
            </div>
            <div className="text-[11px] text-gray-500">or click to browse</div>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>

      {/* Optional account label for files that don't carry an account column. */}
      <input
        value={account}
        onChange={(e) => setAccount(e.target.value)}
        placeholder="Account name (optional)"
        className="mt-2 w-full rounded-md border border-edge bg-ink px-2 py-1 text-[11px] text-gray-200 focus:border-sky-500 focus:outline-none"
      />
      <p className="mt-1 text-[10px] text-gray-600">
        Re-importing is safe — existing transactions stay as they are, only new
        rows are added.
      </p>

      <button
        onClick={handleReset}
        className="mt-1 block text-[10px] text-gray-600 hover:text-rose-400"
      >
        Reset all data
      </button>

      {error && <p className="mt-2 text-[11px] text-rose-400">{error}</p>}

      {summary && !importing && (
        <div className="mt-2 rounded-md border border-edge bg-panel px-2 py-1.5 text-[11px] text-gray-400">
          <span className="text-emerald-400">{summary.imported} new</span>
          <span> · {summary.skipped_duplicates} unchanged</span>
          {summary.cache_hits > 0 && <span> · {summary.cache_hits} cached</span>}
          {summary.llm_cleaned > 0 && <span> · {summary.llm_cleaned} LLM</span>}
          {summary.uncategorized > 0 && (
            <span> · {summary.uncategorized} uncat.</span>
          )}
          {summary.errors?.length > 0 && (
            <span className="text-amber-400"> · {summary.errors.length} skipped</span>
          )}
        </div>
      )}
    </div>
  )
}
