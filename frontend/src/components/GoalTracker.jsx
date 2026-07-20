import { useState } from 'react'
import { useStore } from '../store/useStore'

const money = (n) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n || 0)

// Evaluate a goal against the active scenario's already-computed series (E5).
// Cash goals read the runway; net-worth goals read the macro (yearly) series.
function evaluate(goal, series) {
  if (!series) return { projected: null, onTrack: false }
  let projected = null
  if (goal.kind === 'cash') {
    const idx = Math.min(goal.target_month, series.runway.length - 1)
    projected = series.runway[idx]?.cash ?? null
  } else {
    const year = Math.min(Math.floor(goal.target_month / 12), series.macro.length - 1)
    projected = series.macro[year]?.net_worth ?? null
  }
  return { projected, onTrack: projected != null && projected >= goal.target_amount }
}

const EMPTY = { label: 'New goal', kind: 'net_worth', target_amount: 100000, target_month: 60 }

// E5: target net worth / cash by a future month, with an on/off-track pill
// derived live from the active scenario.
export default function GoalTracker() {
  const goals = useStore((s) => s.goals)
  const series = useStore((s) => s.series)
  const createGoal = useStore((s) => s.createGoal)
  const updateGoal = useStore((s) => s.updateGoal)
  const deleteGoal = useStore((s) => s.deleteGoal)
  const [form, setForm] = useState(null) // {id?} | null

  const input =
    'w-full rounded-md border border-edge bg-ink px-2 py-1 text-xs text-gray-100 focus:border-sky-500 focus:outline-none'

  function openNew() {
    setForm({ ...EMPTY })
  }
  function openEdit(g) {
    setForm({ ...g })
  }
  async function save() {
    const payload = {
      label: form.label.trim() || 'Goal',
      kind: form.kind,
      target_amount: Number(form.target_amount) || 0,
      target_month: Math.max(0, Number(form.target_month) || 0),
    }
    if (form.id != null) await updateGoal(form.id, payload)
    else await createGoal(payload)
    setForm(null)
  }

  return (
    <div className="space-y-1.5">
      {goals.length === 0 && !form && (
        <p className="text-[11px] text-gray-600">
          Set a target net worth or cash balance to track against your plan.
        </p>
      )}

      {goals.map((g) => {
        const { projected, onTrack } = evaluate(g, series)
        return (
          <div
            key={g.id}
            className="flex items-center gap-2 rounded-lg border border-edge bg-panel px-2.5 py-1.5 text-xs"
          >
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                onTrack ? 'bg-emerald-500' : 'bg-rose-500'
              }`}
              title={onTrack ? 'On track' : 'Off track'}
            />
            <div className="min-w-0 flex-1">
              <div className="truncate text-gray-200">{g.label}</div>
              <div className="text-[10px] text-gray-500">
                {money(g.target_amount)} {g.kind === 'cash' ? 'cash' : 'net worth'} · m
                {g.target_month}
                {projected != null && (
                  <span className={onTrack ? 'text-emerald-400' : 'text-rose-400'}>
                    {' '}
                    · proj {money(projected)}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={() => openEdit(g)}
              className="text-gray-500 hover:text-sky-300"
              title="Edit goal"
            >
              ✎
            </button>
            <button
              onClick={() => deleteGoal(g.id)}
              className="text-gray-500 hover:text-rose-400"
              title="Delete goal"
            >
              ✕
            </button>
          </div>
        )
      })}

      {form ? (
        <div className="space-y-1.5 rounded-lg border border-sky-800 bg-sky-950/30 p-2">
          <input
            className={input}
            value={form.label}
            placeholder="Label"
            onChange={(e) => setForm({ ...form, label: e.target.value })}
          />
          <div className="flex gap-1.5">
            <select
              className={input}
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              <option value="net_worth">Net worth</option>
              <option value="cash">Cash</option>
            </select>
            <input
              type="number"
              className={input}
              value={form.target_amount}
              placeholder="Amount"
              onChange={(e) => setForm({ ...form, target_amount: e.target.value })}
            />
          </div>
          <label className="block text-[10px] text-gray-500">
            By month (from now)
            <input
              type="number"
              min="0"
              className={input}
              value={form.target_month}
              onChange={(e) => setForm({ ...form, target_month: e.target.value })}
            />
          </label>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setForm(null)}
              className="text-[11px] text-gray-400 hover:text-gray-200"
            >
              Cancel
            </button>
            <button
              onClick={save}
              className="rounded bg-sky-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-sky-500"
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={openNew}
          className="w-full rounded-lg border border-edge bg-panel py-1.5 text-xs text-gray-300 hover:border-sky-500 hover:text-sky-300"
        >
          + Add goal
        </button>
      )}
    </div>
  )
}
