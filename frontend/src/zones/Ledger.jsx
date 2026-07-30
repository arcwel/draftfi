import { amount } from '../lib/format'
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store/useStore'
import { ResolutionBadge } from '../components/CategoryBadge'
import TransactionModal from '../components/TransactionModal'
import SplitModal from '../components/SplitModal'
import CategoryManager from '../components/CategoryManager'
import {
  LEDGER_COLUMNS,
  clampWidth,
  defaultWidths,
  mergeWidths,
  totalWidth,
} from '../lib/ledgerColumns'

// Zone 4: transaction categorization ledger. Search, sort, and paging run
// server-side over the full database (not just a loaded window).
//
// Column widths are user-set and persisted (see lib/ledgerColumns). The table
// uses a fixed layout so a <colgroup> actually governs the widths — with `auto`
// the browser overrides them from content. Consequence: cells must clip
// explicitly, hence `truncate` on the text columns.
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
  const savedWidths = useStore((s) => s.preferences.ledger_columns)
  const saveLedgerColumns = useStore((s) => s.saveLedgerColumns)

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

  // ---- resizable columns ---------------------------------------------------
  const [widths, setWidths] = useState(() => mergeWidths(savedWidths))
  // Drag handlers read the live widths from a ref: a pointer stream would
  // otherwise capture a stale value from the render it started in.
  const widthsRef = useRef(widths)
  const dragRef = useRef(null)

  useEffect(() => {
    setWidths(mergeWidths(savedWidths))
  }, [savedWidths])

  useEffect(() => {
    widthsRef.current = widths
  }, [widths])

  function beginResize(event, key) {
    // Stop the header's sort button from firing on the same press.
    event.preventDefault()
    event.stopPropagation()
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = { key, from: event.clientX, start: widthsRef.current[key] }
  }

  function moveResize(event) {
    const drag = dragRef.current
    if (!drag) return
    const next = clampWidth(drag.key, drag.start + (event.clientX - drag.from))
    setWidths((current) =>
      current[drag.key] === next ? current : { ...current, [drag.key]: next },
    )
  }

  function endResize(event) {
    if (!dragRef.current) return
    dragRef.current = null
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    // Persist once, on release — not on every pointer move.
    saveLedgerColumns(widthsRef.current)
  }

  function resetColumn(event, key) {
    event.preventDefault()
    event.stopPropagation()
    dragRef.current = null
    const next = { ...widthsRef.current, [key]: defaultWidths()[key] }
    setWidths(next)
    saveLedgerColumns(next)
  }

  const tableWidth = totalWidth(widths)
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

  function Grip({ colKey }) {
    return (
      <span
        role="separator"
        aria-orientation="vertical"
        aria-label="Drag to resize column, double-click to reset"
        title="Drag to resize · double-click to reset"
        onPointerDown={(e) => beginResize(e, colKey)}
        onPointerMove={moveResize}
        onPointerUp={endResize}
        onPointerCancel={endResize}
        onDoubleClick={(e) => resetColumn(e, colKey)}
        className="absolute -right-px top-0 z-10 h-full w-1.5 cursor-col-resize touch-none select-none bg-transparent hover:bg-sky-500/70 active:bg-sky-400"
      />
    )
  }

  function HeaderCell({ col, sortable, align = 'left' }) {
    const active = txSort.by === col.key
    const pad = col.key === 'date' ? 'px-4' : 'px-2'
    return (
      <th
        className={`relative ${pad} py-1.5 font-medium ${
          align === 'right' ? 'text-right' : 'text-left'
        }`}
      >
        {sortable ? (
          <button
            onClick={() => setTxSort(col.key)}
            className={`max-w-full truncate font-medium ${active ? 'text-sky-300' : ''}`}
            title="Sort"
          >
            {col.label}
            {active && (txSort.dir === 'desc' ? ' ↓' : ' ↑')}
          </button>
        ) : (
          <span className="block truncate">{col.label}</span>
        )}
        <Grip colKey={col.key} />
      </th>
    )
  }

  const col = Object.fromEntries(LEDGER_COLUMNS.map((c) => [c.key, c]))

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

      {/* Both axes scroll: widening past the pane pans horizontally rather than
          squeezing the other columns. */}
      <div className="flex-1 overflow-auto">
        {transactions.length === 0 ? (
          <div className="p-6 text-center text-xs text-gray-600">
            {txQuery
              ? 'No transactions match your search.'
              : 'No transactions yet — import a bank CSV from the sidebar.'}
          </div>
        ) : (
          <table
            className="text-sm"
            style={{ tableLayout: 'fixed', width: `${tableWidth}px` }}
          >
            <colgroup>
              {LEDGER_COLUMNS.map((c) => (
                <col key={c.key} style={{ width: `${widths[c.key]}px` }} />
              ))}
            </colgroup>
            <thead className="sticky top-0 z-10 bg-ink text-[11px] uppercase tracking-wide text-gray-500">
              <tr>
                <HeaderCell col={col.date} sortable />
                <HeaderCell col={col.raw} />
                <HeaderCell col={col.merchant} />
                <HeaderCell col={col.amount} sortable align="right" />
                <HeaderCell col={col.category} />
                <HeaderCell col={col.resolution} />
                <HeaderCell col={col.actions} />
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
                  <td className="truncate px-4 py-1.5 text-gray-400">{t.date}</td>
                  <td
                    className="truncate px-2 py-1.5 font-mono text-[11px] text-gray-500"
                    title={t.raw_description}
                  >
                    {t.parent_tx_id != null && (
                      <span className="mr-1 text-sky-500">↳</span>
                    )}
                    {t.raw_description}
                  </td>
                  <td
                    className="truncate px-2 py-1.5 text-gray-200"
                    title={t.clean_merchant || undefined}
                  >
                    <span className="inline-flex max-w-full items-center gap-1.5 align-middle">
                      <span className="truncate">{t.clean_merchant || '—'}</span>
                      {t.note && (
                        <span title={t.note} className="cursor-help text-[11px]">
                          📝
                        </span>
                      )}
                      {(t.tags || []).map((tag) => (
                        <span
                          key={tag}
                          className="shrink-0 rounded-full bg-gray-800 px-1.5 py-0.5 text-[9px] text-gray-400"
                        >
                          {tag}
                        </span>
                      ))}
                    </span>
                  </td>
                  {/* The amount carries its category's colour, so Income reads
                      green, Fees & Interest red, and so on down the ledger. */}
                  <td
                    className="truncate px-2 py-1.5 text-right font-medium"
                    style={{ color: t.category_color || '#94a3b8' }}
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
                        // Follows the column instead of a fixed cap, so widening
                        // the column actually shows the category name.
                        className="w-full rounded-md border border-edge bg-panel px-1.5 py-1 text-xs text-gray-200 focus:border-sky-500 focus:outline-none"
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
                  <td className="truncate px-2 py-1.5">
                    <ResolutionBadge resolution={t.resolution} />
                  </td>
                  <td className="truncate px-3 py-1.5 text-right">
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
