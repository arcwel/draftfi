import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store/useStore'
import { amount as fmtAmount } from '../lib/format'

// Categorize a MERCHANT once and it settles every transaction for it, past and
// future. The list is ordered by transaction count because that is where the
// leverage is: on a real file the top 25 merchants covered 1,169 transactions
// while 810 merchants appeared exactly once.
//
// Keyboard-first on purpose. Hundreds of decisions is only tolerable as a
// rhythm — number keys assign, Enter accepts the suggestion and advances.
export default function MerchantReview({ onClose }) {
  const categories = useStore((s) => s.categories)
  const queue = useStore((s) => s.merchantQueue)
  const loading = useStore((s) => s.merchantQueueLoading)
  const loadQueue = useStore((s) => s.loadMerchantQueue)
  const saveDecisions = useStore((s) => s.saveMerchantDecisions)

  // canonical_key -> category_id chosen in this session (not yet saved).
  const [picked, setPicked] = useState({})
  const [active, setActive] = useState(0)
  const [saving, setSaving] = useState(false)
  const [flash, setFlash] = useState(null)
  const [error, setError] = useState(null)
  const rowRefs = useRef({})

  useEffect(() => {
    loadQueue()
  }, [loadQueue])

  // Uncategorized is never a useful destination here — that's what these rows
  // already are. Number keys map to this palette.
  const palette = useMemo(
    () => categories.filter((c) => c.name !== 'Uncategorized').slice(0, 9),
    [categories],
  )
  const assignable = useMemo(
    () => categories.filter((c) => c.name !== 'Uncategorized'),
    [categories],
  )

  const items = queue.items
  const decided = Object.keys(picked).length
  const coveredTx = items
    .filter((m) => picked[m.canonical_key])
    .reduce((n, m) => n + m.txn_count, 0)

  const choose = useCallback(
    (key, categoryId) => {
      setPicked((current) => {
        if (!categoryId) {
          const next = { ...current }
          delete next[key]
          return next
        }
        return { ...current, [key]: categoryId }
      })
    },
    [],
  )

  // `picked` is local state, so closing throws it away. On a queue whose whole
  // premise is making hundreds of decisions in one sitting, one stray Escape
  // used to silently discard ten minutes of work with no undo.
  const requestClose = useCallback(() => {
    const count = Object.keys(picked).length
    if (count > 0) {
      const ok = window.confirm(
        `Discard ${count} unsaved decision${count === 1 ? '' : 's'}?`,
      )
      if (!ok) return
    }
    onClose()
  }, [picked, onClose])

  const move = useCallback(
    (delta) => {
      setActive((i) => {
        const next = Math.max(0, Math.min(items.length - 1, i + delta))
        const row = rowRefs.current[next]
        if (row) row.scrollIntoView({ block: 'nearest' })
        return next
      })
    },
    [items.length],
  )

  useEffect(() => {
    function onKey(event) {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const tag = event.target.tagName
      const current = items[active]

      if (event.key === 'Escape') return requestClose()

      // Arrows are handled BEFORE the focus check, and preventDefault stops the
      // browser's own behaviour. Previously the handler bailed whenever a
      // <select> had focus — so once the user touched a dropdown with the
      // mouse, ArrowDown stopped moving the cursor and started walking that
      // merchant's category list instead, assigning "Groceries → Travel → Fees"
      // to hundreds of transactions with the row highlight never moving.
      if (event.key === 'ArrowDown' || (event.key === 'j' && tag !== 'SELECT')) {
        event.preventDefault()
        return move(1)
      }
      if (event.key === 'ArrowUp' || (event.key === 'k' && tag !== 'SELECT')) {
        event.preventDefault()
        return move(-1)
      }
      // Everything below assigns a category, so leave real form fields alone.
      if (tag === 'SELECT' || tag === 'INPUT') return
      if (!current) return
      if (event.key === 'Enter') {
        event.preventDefault()
        // Accept whatever is showing — the model's suggestion if there is one.
        const suggested = current.suggested_category_id
        if (suggested) choose(current.canonical_key, suggested)
        return move(1)
      }
      if (event.key === 'Backspace' || event.key === 'Delete') {
        event.preventDefault()
        return choose(current.canonical_key, null)
      }
      const digit = Number(event.key)
      if (digit >= 1 && digit <= palette.length) {
        event.preventDefault()
        choose(current.canonical_key, palette[digit - 1].id)
        move(1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [items, active, palette, choose, move, requestClose])

  async function onApply() {
    setSaving(true)
    setError(null)
    try {
      const decisions = items
        .filter((m) => picked[m.canonical_key])
        .map((m) => ({
          canonical_key: m.canonical_key,
          display_name: m.display_name,
          category_id: picked[m.canonical_key],
        }))
      const result = await saveDecisions(decisions)
      setPicked({})
      setActive(0)
      setFlash(
        `Applied ${result.merchants} merchant${result.merchants === 1 ? '' : 's'} to ${result.transactions} transactions`,
      )
      setTimeout(() => setFlash(null), 4000)
    } catch (err) {
      // Without this the button simply returned to idle and the user had no way
      // to tell whether 612 transactions had just been rewritten or nothing had
      // happened at all. Keep the picked set so they can retry rather than
      // redo ten minutes of decisions.
      setError(err?.message || 'Could not apply these decisions. Nothing was changed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex h-full w-full max-w-5xl flex-col rounded-lg border border-edge bg-ink shadow-2xl">
        <header className="flex items-start justify-between border-b border-edge px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-white">Review merchants</h2>
            <p className="mt-0.5 text-[11px] text-gray-500">
              One decision per merchant applies to every transaction for it, past
              and future.{' '}
              {queue.total_merchants > 0 && (
                <>
                  {queue.total_merchants} merchant
                  {queue.total_merchants === 1 ? '' : 's'} ·{' '}
                  {queue.total_transactions} transactions to resolve
                </>
              )}
            </p>
          </div>
          <button
            onClick={requestClose}
            className="rounded px-2 text-gray-500 hover:text-white"
            title="Close (Esc)"
          >
            ✕
          </button>
        </header>

        {/* The palette doubles as the keyboard legend — number keys are only
            learnable if the mapping is on screen. */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-edge px-4 py-2 text-[10px] text-gray-500">
          <span className="mr-1">Press</span>
          {palette.map((c, i) => (
            <span
              key={c.id}
              className="inline-flex items-center gap-1 rounded border border-edge bg-panel px-1.5 py-0.5"
            >
              <kbd className="font-mono text-gray-300">{i + 1}</kbd>
              <span style={{ color: c.color }}>{c.name}</span>
            </span>
          ))}
          <span className="ml-1">
            · <kbd className="font-mono text-gray-300">↵</kbd> accept suggestion ·{' '}
            <kbd className="font-mono text-gray-300">↑↓</kbd> move ·{' '}
            <kbd className="font-mono text-gray-300">⌫</kbd> clear
          </span>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading && items.length === 0 ? (
            <p className="p-6 text-center text-xs text-gray-600">Loading merchants…</p>
          ) : items.length === 0 ? (
            <p className="p-6 text-center text-xs text-gray-600">
              Nothing left to review — every merchant has a category.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-ink text-[10px] uppercase tracking-wide text-gray-600">
                <tr>
                  <th className="px-4 py-1.5 text-left font-medium">Merchant</th>
                  <th className="px-2 py-1.5 text-right font-medium">Txns</th>
                  <th className="px-2 py-1.5 text-right font-medium">Total</th>
                  <th className="px-2 py-1.5 text-left font-medium">Category</th>
                </tr>
              </thead>
              <tbody>
                {items.map((m, i) => {
                  const chosen = picked[m.canonical_key]
                  const isActive = i === active
                  return (
                    <tr
                      key={m.canonical_key}
                      ref={(el) => (rowRefs.current[i] = el)}
                      onClick={() => setActive(i)}
                      className={`border-t border-edge/60 ${
                        isActive ? 'bg-sky-950/40' : chosen ? 'bg-emerald-950/20' : ''
                      }`}
                    >
                      <td className="px-4 py-1.5">
                        <div className="flex items-center gap-2">
                          {isActive && <span className="text-sky-400">›</span>}
                          <span className="font-medium text-gray-100">
                            {m.display_name}
                          </span>
                          {chosen && <span className="text-[10px] text-emerald-400">✓</span>}
                        </div>
                        <div
                          className="truncate font-mono text-[10px] text-gray-600"
                          title={m.sample_description}
                        >
                          {m.sample_description}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-right text-gray-300">
                        {m.txn_count}
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-right text-gray-400">
                        {fmtAmount(m.total_amount)}
                      </td>
                      <td className="px-2 py-1.5">
                        <select
                          value={chosen || m.suggested_category_id || ''}
                          onChange={(e) => {
                            choose(m.canonical_key, Number(e.target.value) || null)
                            // Hand focus back so the keyboard rhythm resumes on
                            // the queue rather than inside this dropdown.
                            e.target.blur()
                          }}
                          className={`w-full rounded-md border bg-panel px-1.5 py-1 text-xs focus:outline-none ${
                            chosen
                              ? 'border-emerald-600 text-gray-100'
                              : 'border-edge text-gray-400'
                          }`}
                        >
                          <option value="">— choose —</option>
                          {assignable.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </select>
                        {!chosen && m.suggested_category_id && (
                          <span className="mt-0.5 block text-[10px] text-amber-500/80">
                            suggested
                            {m.confidence != null &&
                              ` · ${Math.round(m.confidence * 100)}% sure`}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-edge px-4 py-2.5">
          <span className="max-w-[36rem] truncate text-[11px] text-gray-500" title={error || undefined}>
            {error ? (
              <span className="text-rose-400">✕ {error}</span>
            ) : flash ? (
              <span className="text-emerald-400">{flash}</span>
            ) : (
              `${decided} decided`
            )}
          </span>
          {/* The count lives inside the label: "apply 47 changes" is an informed
              decision, "apply changes" is a leap of faith. */}
          <button
            onClick={onApply}
            disabled={decided === 0 || saving}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-40"
          >
            {saving
              ? 'Applying…'
              : decided === 0
                ? 'Apply'
                : `Apply ${decided} merchant${decided === 1 ? '' : 's'} to ${coveredTx} transaction${coveredTx === 1 ? '' : 's'}`}
          </button>
        </footer>
      </div>
    </div>
  )
}
