import { amount } from '../lib/format'
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store/useStore'
import { ResolutionBadge } from '../components/CategoryBadge'
import TransactionModal from '../components/TransactionModal'
import SplitModal from '../components/SplitModal'
import CategoryManager from '../components/CategoryManager'

// Zone 4: transaction categorization ledger. Search, sort, and paging run
// server-side over the full database (not just a loaded window).
export default function Ledger() {
  const transactions = useStore((s) => s.transactions)
  const total = useStore((s) => s.totalTransactions)
  const categories = useStore((s) => s.categories)
  const overrideCategory = useStore((s) => s.overrideCategory)
  const deleteTransaction = useStore((s) => s.deleteTransaction)
  const unsplitTransaction = useStore((s) => s.unsplitTransaction)
  const txQuery = useStore((s) => s.txQuery)
  const txSort = useStore((s) => s.txSort)
  const txPage = useStore((s) => s.txPage)
  const txPageSize = useStore((s) => s.txPageSize)
  const setTxQuery = useStore((s) => s.setTxQuery)
  const setTxSort = useStore((s) => s.setTxSort)
  const setTxPage = useStore((s) => s.setTxPage)

  const [modal, setModal] = useState(null) // null | {} (add) | transaction (edit)
  const [splitting, setSplitting] = useState(null) // transaction | null
  const [managingCats, setManagingCats] = useState(false)

  // Debounce the search box → server query.
  const [searchDraft, setSearchDraft] = useState(txQuery)
  const debounceRef = useRef(null)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      if (searchDraft !== txQuery) setTxQuery(searchDraft)
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [searchDraft, txQuery, setTxQuery])

  const pages = Math.max(1, Math.ceil(total / txPageSize))

  async function onDelete(t) {
    const label = t.is_split_parent
      ? 'Delete this transaction AND its split parts?'
      : 'Delete this transaction?'
    const ok = window.confirm(
      `${label}\n\n${t.date} · ${t.clean_merchant || t.raw_description} · ${amount(t.amount)}`,
    )
    if (ok) await deleteTransaction(t.id)
  }

  function SortHeader({ col, children, className }) {
    const active = txSort.by === col
    return (
      <th className={className}>
        <button
          onClick={() => setTxSort(col)}
          className={`font-medium ${active ? 'text-sky-300' : ''}`}
          title="Sort"
        >
          {children}
          {active && (txSort.dir === 'desc' ? ' ↓' : ' ↑')}
        </button>
      </th>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center px-4 py-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
          Categorization Ledger
          <span className="ml-2 normal-case text-gray-600">
            {total} transaction{total === 1 ? '' : 's'}
          </span>
        </h2>
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setManagingCats(true)}
            className="rounded-md border border-edge bg-panel px-2.5 py-1 text-xs text-gray-300 hover:border-sky-500 hover:text-sky-300"
          >
            Categories
          </button>
          <input
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            placeholder="Search all transactions…"
            className="w-48 rounded-md border border-edge bg-panel px-2 py-1 text-xs text-gray-200 focus:border-sky-500 focus:outline-none"
          />
          <button
            onClick={() => setModal({})}
            className="rounded-md bg-sky-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-sky-500"
          >
            + Add
          </button>
        </div>
        <div />
      </div>

      <div className="flex-1 overflow-y-auto">
        {transactions.length === 0 ? (
          <div className="p-6 text-center text-xs text-gray-600">
            {txQuery
              ? 'No transactions match your search.'
              : 'No transactions yet — import a bank CSV from the sidebar.'}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-ink text-[11px] uppercase tracking-wide text-gray-500">
              <tr>
                <SortHeader col="date" className="px-4 py-1.5 text-left">
                  Date
                </SortHeader>
                <th className="px-2 py-1.5 text-left font-medium">Raw Descriptor</th>
                <th className="px-2 py-1.5 text-left font-medium">Clean Merchant</th>
                <SortHeader col="amount" className="px-2 py-1.5 text-right">
                  Amount
                </SortHeader>
                <th className="px-2 py-1.5 text-left font-medium">Category</th>
                <th className="px-2 py-1.5 text-left font-medium">Resolution</th>
                <th className="px-3 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr
                  key={t.id}
                  className={`border-t border-edge/60 hover:bg-panel/50 ${
                    t.is_split_parent ? 'opacity-60' : ''
                  }`}
                >
                  <td className="whitespace-nowrap px-4 py-1.5 text-gray-400">
                    {t.date}
                  </td>
                  <td
                    className="max-w-[200px] truncate px-2 py-1.5 font-mono text-[11px] text-gray-500"
                    title={t.raw_description}
                  >
                    {t.parent_tx_id != null && (
                      <span className="mr-1 text-sky-500">↳</span>
                    )}
                    {t.raw_description}
                  </td>
                  <td className="px-2 py-1.5 text-gray-200">
                    <span className="inline-flex items-center gap-1.5">
                      {t.clean_merchant || '—'}
                      {t.note && (
                        <span title={t.note} className="cursor-help text-[11px]">
                          📝
                        </span>
                      )}
                      {(t.tags || []).map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-gray-800 px-1.5 py-0.5 text-[9px] text-gray-400"
                        >
                          {tag}
                        </span>
                      ))}
                    </span>
                  </td>
                  <td
                    className={`whitespace-nowrap px-2 py-1.5 text-right font-medium ${
                      t.amount >= 0 ? 'text-emerald-400' : 'text-gray-300'
                    }`}
                  >
                    {amount(t.amount)}
                  </td>
                  <td className="px-2 py-1.5">
                    {t.is_split_parent ? (
                      <span className="text-[11px] text-gray-500">split ↓</span>
                    ) : (
                      <select
                        value={t.category_id || ''}
                        onChange={(e) => overrideCategory(t.id, Number(e.target.value))}
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
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    <ResolutionBadge resolution={t.resolution} />
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-right">
                    {t.is_split_parent ? (
                      <button
                        onClick={() => unsplitTransaction(t.id)}
                        className="px-1 text-[10px] text-gray-500 hover:text-sky-300"
                        title="Undo split"
                      >
                        unsplit
                      </button>
                    ) : (
                      t.parent_tx_id == null && (
                        <button
                          onClick={() => setSplitting(t)}
                          className="px-1 text-xs text-gray-500 hover:text-sky-300"
                          title="Split across categories"
                        >
                          ⑂
                        </button>
                      )
                    )}
                    <button
                      onClick={() => setModal(t)}
                      className="px-1 text-xs text-gray-500 hover:text-sky-300"
                      title="Edit transaction"
                    >
                      ✎
                    </button>
                    <button
                      onClick={() => onDelete(t)}
                      className="px-1 text-xs text-gray-500 hover:text-rose-400"
                      title="Delete transaction"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {modal && (
        <TransactionModal
          initial={modal.id != null ? modal : null}
          onClose={() => setModal(null)}
        />
      )}
      {splitting && (
        <SplitModal tx={splitting} onClose={() => setSplitting(null)} />
      )}
      {managingCats && <CategoryManager onClose={() => setManagingCats(false)} />}

      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 border-t border-edge px-4 py-1.5 text-xs text-gray-400">
          <button
            disabled={txPage === 0}
            onClick={() => setTxPage(txPage - 1)}
            className="disabled:opacity-40"
          >
            ‹ Prev
          </button>
          <span>
            {txPage + 1} / {pages}
          </span>
          <button
            disabled={txPage >= pages - 1}
            onClick={() => setTxPage(txPage + 1)}
            className="disabled:opacity-40"
          >
            Next ›
          </button>
        </div>
      )}
    </div>
  )
}
