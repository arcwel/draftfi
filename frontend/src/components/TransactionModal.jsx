import { useState } from 'react'
import { useStore } from '../store/useStore'

const inputCls =
  'mt-0.5 w-full rounded-md border border-edge bg-ink px-2 py-1 text-sm text-gray-100 focus:border-sky-500 focus:outline-none'

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-[11px] text-gray-400">{label}</span>
      {children}
    </label>
  )
}

// Add or edit a transaction by hand (cash spending, corrections).
export default function TransactionModal({ initial, onClose }) {
  const categories = useStore((s) => s.categories)
  const createTransaction = useStore((s) => s.createTransaction)
  const updateTransaction = useStore((s) => s.updateTransaction)
  const editing = initial?.id != null

  const [form, setForm] = useState({
    date: initial?.date ?? new Date().toISOString().slice(0, 10),
    amount: initial?.amount ?? '',
    raw_description: initial?.raw_description ?? '',
    clean_merchant: initial?.clean_merchant ?? '',
    account_name: initial?.account_name ?? 'Manual Entry',
    category_id: initial?.category_id ?? '',
    note: initial?.note ?? '',
    tags: (initial?.tags ?? []).join(', '),
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function save() {
    setError(null)
    const amount = Number(form.amount)
    if (!form.raw_description.trim()) return setError('Description is required.')
    if (Number.isNaN(amount) || amount === 0)
      return setError('Amount must be a non-zero number (negative = spending).')
    setBusy(true)
    try {
      const payload = {
        date: form.date,
        amount,
        raw_description: form.raw_description.trim(),
        clean_merchant: form.clean_merchant.trim() || null,
        account_name: form.account_name.trim() || 'Manual Entry',
        category_id: form.category_id === '' ? null : Number(form.category_id),
        note: form.note.trim() || null,
        tags: form.tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      }
      if (editing) await updateTransaction(initial.id, payload)
      else await createTransaction(payload)
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
        <h3 className="mb-3 text-sm font-semibold text-white">
          {editing ? 'Edit Transaction' : 'Add Transaction'}
        </h3>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Date">
            <input
              type="date"
              className={inputCls}
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </Field>
          <Field label="Amount (negative = spending)">
            <input
              type="number"
              step="0.01"
              className={inputCls}
              value={form.amount}
              placeholder="-12.50"
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </Field>
          <div className="col-span-2">
            <Field label="Description">
              <input
                className={inputCls}
                value={form.raw_description}
                placeholder="e.g. Farmers market"
                onChange={(e) =>
                  setForm({ ...form, raw_description: e.target.value })
                }
              />
            </Field>
          </div>
          <Field label="Merchant (optional)">
            <input
              className={inputCls}
              value={form.clean_merchant}
              onChange={(e) => setForm({ ...form, clean_merchant: e.target.value })}
            />
          </Field>
          <Field label="Account">
            <input
              className={inputCls}
              value={form.account_name}
              onChange={(e) => setForm({ ...form, account_name: e.target.value })}
            />
          </Field>
          <div className="col-span-2">
            <Field label="Category">
              <select
                className={inputCls}
                value={form.category_id}
                onChange={(e) => setForm({ ...form, category_id: e.target.value })}
              >
                <option value="">Uncategorized</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="col-span-2">
            <Field label="Note (optional)">
              <input
                className={inputCls}
                value={form.note}
                placeholder="e.g. reimbursable — submit to HR"
                onChange={(e) => setForm({ ...form, note: e.target.value })}
              />
            </Field>
          </div>
          <div className="col-span-2">
            <Field label="Tags (comma-separated, optional)">
              <input
                className={inputCls}
                value={form.tags}
                placeholder="e.g. travel, reimbursable"
                onChange={(e) => setForm({ ...form, tags: e.target.value })}
              />
            </Field>
          </div>
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
            disabled={busy}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {busy ? 'Saving…' : editing ? 'Save Changes' : 'Add Transaction'}
          </button>
        </div>
      </div>
    </div>
  )
}
