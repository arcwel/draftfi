import { useState } from 'react'
import { useStore } from '../store/useStore'
import Sparkline from './Sparkline'

const money = (n) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n || 0)

const signed = (n) => `${n >= 0 ? '+' : '−'}${money(Math.abs(n))}`

const monthLabel = (ym) => {
  const [y, m] = ym.split('-')
  return new Date(Number(y), Number(m) - 1).toLocaleString('en-US', {
    month: 'short',
    year: 'numeric',
  })
}

// Zone: monthly budget by category + how the active scenario reshapes it.
export default function BudgetPanel() {
  const budget = useStore((s) => s.budget)
  const trends = useStore((s) => s.trends)
  const budgetMonth = useStore((s) => s.budgetMonth)
  const setBudgetMonth = useStore((s) => s.setBudgetMonth)
  const setCategoryBudget = useStore((s) => s.setCategoryBudget)

  if (!budget) {
    return (
      <div className="rounded-xl border border-edge bg-panel/60 p-4 text-xs text-gray-600">
        Import a statement to see your monthly budget.
      </div>
    )
  }

  const expenses = budget.categories.filter((c) => !c.is_income)
  const incomes = budget.categories.filter((c) => c.is_income)
  const maxExpense = Math.max(1, ...expenses.map((c) => c.monthly_amount))
  const s = budget.scenario
  const scenarioActive =
    s.income_adjustment_pct !== 0 || s.recurring_milestone_cost > 0 || s.one_time_cost > 0

  // Per-category monthly series (for the row sparklines).
  const seriesByCat = {}
  for (const c of trends?.categories || []) {
    seriesByCat[c.category_id] = c.series.map((p) => p.amount)
  }
  const months = budget.available_months || []

  return (
    <div className="rounded-xl border border-edge bg-panel/60 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">
          Monthly Budget
          <span className="ml-2 text-[11px] font-normal text-gray-500">
            {budgetMonth
              ? monthLabel(budgetMonth)
              : `avg of ${budget.months_observed} month${budget.months_observed === 1 ? '' : 's'}`}
          </span>
        </h3>
        {months.length > 0 && (
          <select
            value={budgetMonth ?? ''}
            onChange={(e) => setBudgetMonth(e.target.value || null)}
            className="rounded-md border border-edge bg-ink px-2 py-1 text-[11px] text-gray-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All months (avg)</option>
            {months.map((m) => (
              <option key={m} value={m}>
                {monthLabel(m)}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Totals */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        <Stat label="Income / mo" value={money(budget.total_monthly_income)} tone="pos" />
        <Stat label="Spending / mo" value={money(budget.total_monthly_expense)} tone="neg" />
        <Stat
          label="Net / mo"
          value={signed(budget.total_monthly_net)}
          tone={budget.total_monthly_net >= 0 ? 'pos' : 'neg'}
        />
      </div>

      {/* Scenario impact */}
      {scenarioActive && (
        <div className="mb-3 rounded-lg border border-sky-900 bg-sky-950/40 p-2.5 text-xs">
          <div className="mb-1 font-medium text-sky-300">Scenario impact on budget</div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-gray-300">
            {s.income_adjustment_pct !== 0 && (
              <span>
                Income {s.income_adjustment_pct > 0 ? '+' : ''}
                {s.income_adjustment_pct}% → {money(s.scenario_monthly_income)}/mo
              </span>
            )}
            {s.recurring_milestone_cost > 0 && (
              <span className="text-rose-300">
                + {money(s.recurring_milestone_cost)}/mo milestone payments
              </span>
            )}
            {s.one_time_cost > 0 && (
              <span className="text-amber-300">
                {money(s.one_time_cost)} one-time
              </span>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="text-gray-400">Net / mo:</span>
            <span className="text-gray-300">{signed(s.baseline_monthly_net)}</span>
            <span className="text-gray-500">→</span>
            <span
              className={`font-semibold ${s.scenario_monthly_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}
            >
              {signed(s.scenario_monthly_net)}
            </span>
            <span
              className={`ml-1 rounded px-1.5 py-0.5 text-[10px] ${
                s.net_delta >= 0
                  ? 'bg-emerald-950 text-emerald-300'
                  : 'bg-rose-950 text-rose-300'
              }`}
            >
              {signed(s.net_delta)}/mo
            </span>
          </div>
          {s.milestones.some((m) => m.monthly_amount > 0) && (
            <div className="mt-1 text-[11px] text-gray-500">
              {s.milestones
                .filter((m) => m.monthly_amount > 0)
                .map((m) => `${m.label}: ${money(m.monthly_amount)}/mo (mo ${m.start_month}–${m.end_month})`)
                .join(' · ')}
            </div>
          )}
        </div>
      )}

      {/* Per-category spending with editable budget targets */}
      <div className="space-y-1">
        {expenses.length === 0 && (
          <div className="py-2 text-center text-xs text-gray-600">
            No categorized spending yet.
          </div>
        )}
        {expenses.map((c) => (
          <CategoryRow
            key={c.category_id ?? c.name}
            cat={c}
            maxExpense={maxExpense}
            series={seriesByCat[c.category_id]}
            onSetBudget={(amt, rollover) =>
              setCategoryBudget(c.category_id, amt, rollover)
            }
          />
        ))}
      </div>

      {incomes.length > 0 && (
        <div className="mt-3 border-t border-edge pt-2">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Income sources
          </div>
          {incomes.map((c) => (
            <div
              key={c.category_id ?? c.name}
              className="flex items-center justify-between py-0.5 text-xs"
            >
              <span className="flex items-center gap-1.5">
                <Dot color={c.color} />
                {c.name}
              </span>
              <span className="text-emerald-400">{money(c.monthly_amount)}/mo</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, tone }) {
  const color =
    tone === 'pos' ? 'text-emerald-400' : tone === 'neg' ? 'text-rose-300' : 'text-gray-200'
  return (
    <div className="rounded-lg border border-edge bg-ink px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-sm font-semibold ${color}`}>{value}</div>
    </div>
  )
}

function Dot({ color }) {
  return (
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{ background: color || '#64748b' }}
    />
  )
}

function CategoryRow({ cat, maxExpense, series, onSetBudget }) {
  const [editing, setEditing] = useState(false)
  const hasBudget = cat.monthly_budget != null
  // Fill relative to the effective budget (incl. rollover) if set, else largest.
  const budgetForBar = cat.effective_budget ?? cat.monthly_budget
  const denom = hasBudget && budgetForBar > 0 ? budgetForBar : maxExpense
  const pct = Math.min(100, (cat.monthly_amount / denom) * 100)
  const barColor = cat.over_budget ? '#ef4444' : cat.color

  return (
    <div className="rounded-md px-1 py-1 hover:bg-ink/60">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-gray-200">
          <Dot color={cat.color} />
          {cat.name}
          <span className="text-[10px] text-gray-600">{cat.transactions} tx</span>
        </span>
        <span className="flex items-center gap-2">
          {series && series.length > 1 && (
            <Sparkline values={series} color={cat.color} />
          )}
          <span className="font-medium text-gray-200">
            {money(cat.monthly_amount)}/mo
          </span>
          {editing ? (
            <input
              autoFocus
              type="number"
              defaultValue={cat.monthly_budget ?? ''}
              placeholder="budget"
              onBlur={(e) => {
                const v = e.target.value.trim()
                onSetBudget(v === '' ? null : Number(v), cat.rollover)
                setEditing(false)
              }}
              onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
              className="w-20 rounded border border-sky-500 bg-ink px-1.5 py-0.5 text-[11px] text-gray-100 focus:outline-none"
            />
          ) : (
            <button
              onClick={() => setEditing(true)}
              className={`rounded px-1.5 py-0.5 text-[10px] ${
                hasBudget
                  ? cat.over_budget
                    ? 'bg-rose-950 text-rose-300'
                    : 'bg-gray-800 text-gray-400'
                  : 'text-gray-600 hover:text-sky-300'
              }`}
              title="Set monthly budget target"
            >
              {hasBudget ? `budget ${money(cat.monthly_budget)}` : '+ budget'}
            </button>
          )}
          {hasBudget && (
            <button
              onClick={() => onSetBudget(cat.monthly_budget, !cat.rollover)}
              className={`rounded px-1 text-[10px] ${
                cat.rollover ? 'text-sky-300' : 'text-gray-600 hover:text-gray-400'
              }`}
              title="Roll unspent budget into next month"
            >
              ↻
            </button>
          )}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-ink">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
      {hasBudget && cat.budget_used_pct != null && (
        <div className="mt-0.5 flex items-center justify-end gap-2 text-[10px] text-gray-500">
          {cat.carried_over != null && cat.carried_over > 0 && (
            <span className="text-sky-400">
              +{money(cat.carried_over)} rolled over
            </span>
          )}
          <span>
            {cat.budget_used_pct}% of budget
            {cat.over_budget && <span className="text-rose-400"> · over</span>}
          </span>
        </div>
      )}
    </div>
  )
}
