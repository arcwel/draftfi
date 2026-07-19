import { useState } from 'react'
import { useStore } from '../store/useStore'

// Canonical fields the backend understands. Description + a date + an amount
// (single, or a debit/credit pair) are required.
const FIELDS = [
  { key: 'date', label: 'Date', required: true },
  { key: 'description', label: 'Description', required: true },
  { key: 'amount', label: 'Amount (single column)', required: false },
  { key: 'debit', label: 'Debit / Money out', required: false },
  { key: 'credit', label: 'Credit / Money in', required: false },
  { key: 'account', label: 'Account (optional)', required: false },
]

// Shown when a CSV's columns can't be auto-detected: the user maps them once,
// and the layout is remembered for that bank going forward.
export default function MappingModal() {
  const info = useStore((s) => s.mappingNeeded)
  const submitMapping = useStore((s) => s.submitMapping)
  const cancelMapping = useStore((s) => s.cancelMapping)
  const [map, setMap] = useState({})
  const [busy, setBusy] = useState(false)

  if (!info) return null

  const hasAmount = map.amount || map.debit || map.credit
  const valid = map.date && map.description && hasAmount

  async function save() {
    if (!valid) return
    setBusy(true)
    // Drop empty selections before sending.
    const clean = Object.fromEntries(
      Object.entries(map).filter(([, v]) => v),
    )
    await submitMapping(clean)
    setBusy(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-edge bg-panel p-4 shadow-xl">
        <h3 className="text-sm font-semibold text-white">Map your columns</h3>
        <p className="mb-3 mt-1 text-xs text-gray-500">
          {"We couldn't auto-detect this file's layout. Match each field to a " +
            "column — we'll remember it for this bank next time."}
        </p>

        {/* Preview of the file's first rows */}
        <div className="mb-3 max-h-40 overflow-auto rounded-md border border-edge">
          <table className="w-full text-[11px]">
            <thead className="bg-ink text-gray-400">
              <tr>
                {info.headers.map((h, i) => (
                  <th key={i} className="whitespace-nowrap px-2 py-1 text-left">
                    {h || `Col ${i + 1}`}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {info.sample_rows.map((row, ri) => (
                <tr key={ri} className="border-t border-edge/50">
                  {info.headers.map((_, ci) => (
                    <td key={ci} className="whitespace-nowrap px-2 py-1 text-gray-400">
                      {row[ci] ?? ''}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Field → column selectors */}
        <div className="grid grid-cols-2 gap-2">
          {FIELDS.map((f) => (
            <label key={f.key} className="flex items-center gap-2 text-xs">
              <span className="w-40 text-gray-400">
                {f.label}
                {f.required && <span className="text-rose-400"> *</span>}
              </span>
              <select
                value={map[f.key] ?? ''}
                onChange={(e) => setMap({ ...map, [f.key]: e.target.value })}
                className="flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-gray-100 focus:border-sky-500 focus:outline-none"
              >
                <option value="">—</option>
                {info.headers.map((h, i) => (
                  <option key={i} value={h}>
                    {h || `Col ${i + 1}`}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>

        <p className="mt-2 text-[11px] text-gray-600">
          Provide a single Amount column, or a Debit/Credit pair.
        </p>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={cancelMapping}
            className="rounded-md px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={!valid || busy}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {busy ? 'Importing…' : 'Import with this mapping'}
          </button>
        </div>
      </div>
    </div>
  )
}
