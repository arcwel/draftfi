import { useState } from 'react'

const EMPTY = {
  label: 'Income change',
  month: 6,
  kind: 'income',
  mode: 'set',
  amount: 0,
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="text-[11px] text-gray-400">{label}</span>
      {children}
      {hint && <span className="block text-[10px] text-gray-600">{hint}</span>}
    </label>
  )
}

// E2: modal for a step change to monthly income or expense from a given month.
export default function EventModal({ initial, onSave, onClose }) {
  const [e, setE] = useState({ ...EMPTY, ...(initial || {}) })
  const num = (v) => (v === '' ? 0 : Number(v))
  const input =
    'mt-0.5 w-full rounded-md border border-edge bg-ink px-2 py-1 text-sm text-gray-100 focus:border-sky-500 focus:outline-none'

  const amountHint =
    e.mode === 'set'
      ? `new monthly ${e.kind} from month ${e.month}`
      : `add to monthly ${e.kind} (negative to reduce)`

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-edge bg-panel p-4 shadow-xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <h3 className="mb-3 text-sm font-semibold text-white">
          {initial ? 'Edit Change Event' : 'Add Income / Expense Change'}
        </h3>

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Field label="Label">
              <input
                className={input}
                value={e.label}
                onChange={(ev) => setE({ ...e, label: ev.target.value })}
              />
            </Field>
          </div>
          <Field label="Applies to">
            <select
              className={input}
              value={e.kind}
              onChange={(ev) => setE({ ...e, kind: ev.target.value })}
            >
              <option value="income">Income</option>
              <option value="expense">Expense</option>
            </select>
          </Field>
          <Field label="Change type">
            <select
              className={input}
              value={e.mode}
              onChange={(ev) => setE({ ...e, mode: ev.target.value })}
            >
              <option value="set">Set to (absolute)</option>
              <option value="delta">Adjust by (+/-)</option>
            </select>
          </Field>
          <Field label="Start month" hint="months from now (0 = today)">
            <input
              type="number"
              min="0"
              className={input}
              value={e.month}
              onChange={(ev) => setE({ ...e, month: num(ev.target.value) })}
            />
          </Field>
          <Field label="Amount" hint={amountHint}>
            <input
              type="number"
              className={input}
              value={e.amount}
              onChange={(ev) => setE({ ...e, amount: num(ev.target.value) })}
            />
          </Field>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(e)}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            Save Event
          </button>
        </div>
      </div>
    </div>
  )
}
