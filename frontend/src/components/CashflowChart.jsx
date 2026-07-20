import { money } from '../lib/format'
import { memo, useMemo } from 'react'
import {
  Bar,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { LegendItem } from './RunwayChart'

// Month-over-month cash flow: income vs. spending bars with a net line (D3),
// giving the actuals-over-time view that complements the forward forecast.
function CashflowChart({ trends, onSelectMonth, selectedMonth }) {
  const data = useMemo(
    () => (trends?.cashflow || []).map((p) => ({ ...p })),
    [trends],
  )

  if (!trends || data.length === 0) {
    return (
      <div className="rounded-xl border border-edge bg-panel/60 p-4 text-xs text-gray-600">
        Import a few months of statements to see spending trends.
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-edge bg-panel/60 p-3">
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-white">
          Cash Flow
          <span className="ml-2 text-[11px] font-normal text-gray-500">
            income vs. spending · {data.length} month{data.length === 1 ? '' : 's'}
          </span>
        </h3>
      </div>
      <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-gray-400">
        <LegendItem color="#22c55e">Income</LegendItem>
        <LegendItem color="#f43f5e">Spending</LegendItem>
        <LegendItem color="#e5e7eb">Net</LegendItem>
        <span className="ml-auto text-gray-600">click a month to focus the budget</span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart
          data={data}
          margin={{ top: 5, right: 8, left: 8, bottom: 0 }}
          onClick={(e) => {
            const m = e?.activeLabel
            if (m && onSelectMonth) onSelectMonth(m === selectedMonth ? null : m)
          }}
        >
          <XAxis
            dataKey="month"
            stroke="#4b5563"
            tick={{ fontSize: 11, fill: '#9ca3af' }}
          />
          <YAxis
            stroke="#4b5563"
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            tickFormatter={(v) => `${Math.round(v / 1000)}k`}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: '#111827',
              border: '1px solid #1f2937',
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(v, k) => [money(v), k]}
            cursor={{ fill: '#1f2937', opacity: 0.4 }}
          />
          <Bar dataKey="income" fill="#22c55e" radius={[3, 3, 0, 0]} maxBarSize={26} />
          <Bar dataKey="expense" fill="#f43f5e" radius={[3, 3, 0, 0]} maxBarSize={26} />
          <Line
            type="monotone"
            dataKey="net"
            stroke="#e5e7eb"
            strokeWidth={2}
            dot={{ r: 2 }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export default memo(CashflowChart)
