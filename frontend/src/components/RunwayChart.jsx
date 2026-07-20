import { money } from '../lib/format'
import { memo, useMemo } from 'react'
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

// Chart A — Tactical Runway (PRD 5.1). Amber/red highlight below safety floor.
function RunwayChart({ series, compare }) {
  const data = useMemo(() => {
    if (!series) return []
    const baseByMonth = compare
      ? Object.fromEntries(compare.base.runway.map((p) => [p.month, p.cash]))
      : null
    return series.runway.map((p) => ({
      month: p.month,
      cash: p.cash,
      danger: p.below_floor ? p.cash : null,
      base: baseByMonth ? baseByMonth[p.month] : null,
    }))
  }, [series, compare])

  if (!series) return <ChartSkeleton />

  const floor = series.safety_floor
  const failure = series.failure_month
  const endCash = series.runway.length ? series.runway[series.runway.length - 1].cash : 0
  const endDelta =
    compare && compare.base.runway.length
      ? endCash - compare.base.runway[compare.base.runway.length - 1].cash
      : null

  return (
    <div className="h-full">
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-white">
          Tactical Cash Runway
          <span className="ml-2 text-[11px] font-normal text-gray-500">
            liquid cash · {series.runway.length - 1} months
          </span>
        </h3>
        {failure != null ? (
          <span className="text-xs font-medium text-rose-400">
            ⚠ Dips below floor at month {failure}
          </span>
        ) : (
          <span className="text-xs text-emerald-400">✓ Stays above safety floor</span>
        )}
      </div>

      <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-gray-400">
        <LegendItem color="#38bdf8">This scenario</LegendItem>
        {compare && <LegendItem color="#94a3b8" dashed>Base Plan</LegendItem>}
        <LegendItem color="#f59e0b" dashed>Safety floor</LegendItem>
        {failure != null && <LegendItem color="#ef4444">Below floor</LegendItem>}
        {endDelta != null && (
          <span className="ml-auto text-gray-400">
            End vs Base:{' '}
            <span className={endDelta >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {endDelta >= 0 ? '+' : ''}
              {money(endDelta)}
            </span>
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 5, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="cashFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="month"
            stroke="#4b5563"
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            tickFormatter={(m) => `${m}m`}
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
            formatter={(v) => money(v)}
            labelFormatter={(m) => `Month ${m}`}
          />
          <ReferenceLine
            y={floor}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            label={{
              value: `Safety floor ${money(floor)}`,
              fill: '#f59e0b',
              fontSize: 10,
              position: 'insideBottomRight',
            }}
          />
          <Area
            type="monotone"
            dataKey="cash"
            stroke="#38bdf8"
            strokeWidth={2}
            fill="url(#cashFill)"
            isAnimationActive={false}
          />
          {/* Red overlay for months below the floor. */}
          <Line
            type="monotone"
            dataKey="danger"
            stroke="#ef4444"
            strokeWidth={2.5}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
          {compare && (
            <Line
              type="monotone"
              dataKey="base"
              stroke="#94a3b8"
              strokeWidth={1.5}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export function LegendItem({ color, dashed, children }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className="inline-block h-0.5 w-4 rounded"
        style={{
          background: dashed
            ? `repeating-linear-gradient(90deg, ${color} 0 4px, transparent 4px 7px)`
            : color,
        }}
      />
      {children}
    </span>
  )
}

function ChartSkeleton() {
  return (
    <div className="flex h-[220px] items-center justify-center text-xs text-gray-600">
      Import a statement or adjust parameters to simulate…
    </div>
  )
}

export default memo(RunwayChart)
