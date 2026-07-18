import { useState } from 'react'

const EMPTY = {
  label: 'New Purchase',
  target_month: 6,
  down_payment: 0,
  recurring_payment: 0,
  recurring_months: 0,
  asset_value: 0,
  debt_incurred: 0,
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

// Modal tray to inject a high-ticket milestone (PRD 4.2).
export default function MilestoneModal({ initial, onSave, onClose }) {
  const [m, setM] = useState({ ...EMPTY, ...(initial || {}) })
  const num = (v) => (v === '' ? 0 : Number(v))
  const input =
    'mt-0.5 w-full rounded-md border border-edge bg-ink px-2 py-1 text-sm text-gray-100 focus:border-sky-500 focus:outline-none'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-edge bg-panel p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-3 text-sm font-semibold text-white">
          {initial ? 'Edit Milestone' : 'Add Milestone / Large Purchase'}
        </h3>

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Field label="Label">
              <input
                className={input}
                value={m.label}
                onChange={(e) => setM({ ...m, label: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Target month" hint="months from now (0 = today)">
            <input
              type="number"
              min="0"
              className={input}
              value={m.target_month}
              onChange={(e) => setM({ ...m, target_month: num(e.target.value) })}
            />
          </Field>
          <Field label="Down payment" hint="one-time cash outflow">
            <input
              type="number"
              className={input}
              value={m.down_payment}
              onChange={(e) => setM({ ...m, down_payment: num(e.target.value) })}
            />
          </Field>
          <Field label="Recurring payment" hint="monthly (lease / loan)">
            <input
              type="number"
              className={input}
              value={m.recurring_payment}
              onChange={(e) => setM({ ...m, recurring_payment: num(e.target.value) })}
            />
          </Field>
          <Field label="Recurring months" hint="term length">
            <input
              type="number"
              min="0"
              className={input}
              value={m.recurring_months}
              onChange={(e) => setM({ ...m, recurring_months: num(e.target.value) })}
            />
          </Field>
          <Field label="Asset value" hint="added to net worth">
            <input
              type="number"
              className={input}
              value={m.asset_value}
              onChange={(e) => setM({ ...m, asset_value: num(e.target.value) })}
            />
          </Field>
          <Field label="Debt incurred" hint="structural debt added">
            <input
              type="number"
              className={input}
              value={m.debt_incurred}
              onChange={(e) => setM({ ...m, debt_incurred: num(e.target.value) })}
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
            onClick={() => onSave(m)}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            Save Milestone
          </button>
        </div>
      </div>
    </div>
  )
}
