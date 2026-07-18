import { useMemo, useState } from 'react'
import { useStore } from '../store/useStore'
import { ResolutionBadge } from '../components/CategoryBadge'

const money = (n) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0)

const PAGE = 25

// Zone 4: transaction categorization ledger (PRD 4.3).
export default function Ledger() {
  const transactions = useStore((s) => s.transactions)
  const total = useStore((s) => s.totalTransactions)
  const categories = useStore((s) => s.categories)
  const overrideCategory = useStore((s) => s.overrideCategory)
  const [page, setPage] = useState(0)
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return transactions
    return transactions.filter(
      (t) =>
        t.raw_description.toLowerCase().includes(q) ||
        (t.clean_merchant || '').toLowerCase().includes(q) ||
        (t.category_name || '').toLowerCase().includes(q),
    )
  }, [transactions, filter])

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE))
  const current = Math.min(page, pages - 1)
  const rows = filtered.slice(current * PAGE, current * PAGE + PAGE)

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 py-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
          Categorization Ledger
          <span className="ml-2 normal-case text-gray-600">{total} transactions</span>
        </h2>
        <input
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value)
            setPage(0)
          }}
          placeholder="Filter…"
          className="w-40 rounded-md border border-edge bg-panel px-2 py-1 text-xs text-gray-200 focus:border-sky-500 focus:outline-none"
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {rows.length === 0 ? (
          <div className="p-6 text-center text-xs text-gray-600">
            No transactions yet — import a bank CSV from the sidebar.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-ink text-[11px] uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-1.5 text-left font-medium">Date</th>
                <th className="px-2 py-1.5 text-left font-medium">Raw Descriptor</th>
                <th className="px-2 py-1.5 text-left font-medium">Clean Merchant</th>
                <th className="px-2 py-1.5 text-right font-medium">Amount</th>
                <th className="px-2 py-1.5 text-left font-medium">Category</th>
                <th className="px-4 py-1.5 text-left font-medium">Resolution</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id} className="border-t border-edge/60 hover:bg-panel/50">
                  <td className="whitespace-nowrap px-4 py-1.5 text-gray-400">
                    {t.date}
                  </td>
                  <td
                    className="max-w-[220px] truncate px-2 py-1.5 font-mono text-[11px] text-gray-500"
                    title={t.raw_description}
                  >
                    {t.raw_description}
                  </td>
                  <td className="px-2 py-1.5 text-gray-200">
                    {t.clean_merchant || '—'}
                  </td>
                  <td
                    className={`whitespace-nowrap px-2 py-1.5 text-right font-medium ${
                      t.amount >= 0 ? 'text-emerald-400' : 'text-gray-300'
                    }`}
                  >
                    {money(t.amount)}
                  </td>
                  <td className="px-2 py-1.5">
                    <select
                      value={t.category_id || ''}
                      onChange={(e) =>
                        overrideCategory(t.id, Number(e.target.value))
                      }
                      className="max-w-[150px] rounded-md border border-edge bg-panel px-1.5 py-1 text-xs text-gray-200 focus:border-sky-500 focus:outline-none"
                    >
                      <option value="" disabled>
                        Set category…
                      </option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-1.5">
                    <ResolutionBadge resolution={t.resolution} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 border-t border-edge px-4 py-1.5 text-xs text-gray-400">
          <button
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
            className="disabled:opacity-40"
          >
            ‹ Prev
          </button>
          <span>
            {current + 1} / {pages}
          </span>
          <button
            disabled={current >= pages - 1}
            onClick={() => setPage(current + 1)}
            className="disabled:opacity-40"
          >
            Next ›
          </button>
        </div>
      )}
    </div>
  )
}
