import { amount } from '../lib/format'
import { useState } from 'react'
import { useStore } from '../store/useStore'

const inputCls =
  'w-full rounded-md border border-edge bg-ink px-2 py-1 text-sm text-gray-100 focus:border-sky-500 focus:outline-none'

// Split one transaction across categories (amounts must sum to the original).
export default function SplitModal({ tx, onClose }) {
  const categories = useStore((s) => s.categories)
  const splitTransaction = useStore((s) => s.splitTransaction)
  const [parts, setParts] = useState([
    { amount: (tx.amount / 2).toFixed(2), category_id: tx.category_id ?? '' },
    { amount: (tx.amount / 2).toFixed(2), category_id: '' },
  ])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const sum = parts.reduce((acc, p) => acc + (Number(p.amount) || 0), 0)
  const remainder = tx.amount - sum
  const balanced = Math.abs(remainder) <= 0.01

  function setPart(i, patch) {
    setParts(parts.map((p, idx) => (idx === i ? { ...p, ...patch } : p)))
  }

  async function save() {
    if (!balanced) return
    setBusy(true)
    setError(null)
    try {
      await splitTransaction(
        tx.id,
        parts.map((p) => ({
          amount: Number(p.amount),
          category_id: p.category_id === '' ? null : Number(p.category_id),
        })),
      )
      onClose()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-edge bg-panel p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-1 text-sm font-semibold text-white">Split Transaction</h3>
        <p className="mb-3 text-xs text-gray-500">
          {tx.clean_merchant || tx.raw_description} · {amount(tx.amount)}
        </p>

        <div className="space-y-2">
          {parts.map((p, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="number"
                step="0.01"
                className={`${inputCls} w-28`}
                value={p.amount}
                onChange={(e) => setPart(i, { amount: e.target.value })}
              />
              <select
                className={inputCls}
                value={p.category_id}
                onChange={(e) => setPart(i, { category_id: e.target.value })}
              >
                <option value="">Uncategorized</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              {parts.length > 2 && (
                <button
                  onClick={() => setParts(parts.filter((_, idx) => idx !== i))}
                  className="text-gray-500 hover:text-rose-400"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>

        <div className="mt-2 flex items-center justify-between text-xs">
          <button
            onClick={() =>
              setParts([...parts, { amount: remainder.toFixed(2), category_id: '' }])
            }
            disabled={parts.length >= 10}
            className="text-sky-300 hover:text-sky-200 disabled:opacity-50"
          >
            + Add part
          </button>
          <span className={balanced ? 'text-emerald-400' : 'text-amber-400'}>
            {balanced
              ? '✓ Amounts balance'
              : `${amount(remainder)} left to allocate`}
          </span>
        </div>

        {error && <p className="mt-2 text-[11px] text-rose-400">{error}</p>}

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={busy || !balanced}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {busy ? 'Splitting…' : 'Split'}
          </button>
        </div>
      </div>
    </div>
  )
}
