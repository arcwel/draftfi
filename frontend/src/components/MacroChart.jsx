import { money } from '../lib/format'
import { memo, useMemo, useState } from 'react'
import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { LegendItem } from './RunwayChart'

// Chart B — Macro Wealth (PRD 5.2). Stacked assets-over-debt; dashed base line.
function MacroChart({ series, compare }) {
  // E3: toggle nominal vs. inflation-adjusted (today's dollars) net worth.
  const [real, setReal] = useState(false)

  const data = useMemo(() => {
    if (!series) return []
    const baseByYear = compare
      ? Object.fromEntries(
          compare.base.macro.map((p) => [
            p.year,
            real ? p.real_net_worth : p.net_worth,
          ]),
        )
      : null
    return series.macro.map((p) => ({
      year: p.year,
      assets: p.total_assets,
      debt: p.remaining_debt,
      net: real ? p.real_net_worth : p.net_worth,
      baseNet: baseByYear ? baseByYear[p.year] : null,
    }))
  }, [series, compare, real])

  if (!series) return null

  const finalNet = data.length ? data[data.length - 1].net : 0

  return (
    <div className="h-full">
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-white">
          Macro Wealth
          <span className="ml-2 text-[11px] font-normal text-gray-500">
            {series.macro.length - 1} years{real ? " · today's $" : ''}
          </span>
        </h3>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setReal((v) => !v)}
            className={`rounded px-1.5 py-0.5 text-[10px] ${
              real
                ? 'bg-sky-600 text-white'
                : 'border border-edge text-gray-400 hover:text-gray-200'
            }`}
            title="Show net worth in today's dollars (inflation-adjusted)"
          >
            Real $
          </button>
          <span className="text-xs text-gray-400">
            Net worth in yr {series.macro.length - 1}:{' '}
            <span className="font-medium text-emerald-400">{money(finalNet)}</span>
          </span>
        </div>
      </div>

      <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-gray-400">
        <LegendItem color="#22c55e">Total assets</LegendItem>
        <LegendItem color="#a855f7">Structural debt</LegendItem>
        <LegendItem color="#e5e7eb">Net worth</LegendItem>
        {compare && <LegendItem color="#94a3b8" dashed>Base Plan net worth</LegendItem>}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 5, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="assetFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#22c55e" stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="debtFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#a855f7" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#a855f7" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="year"
            stroke="#4b5563"
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            tickFormatter={(y) => `${y}y`}
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
            labelFormatter={(y) => `Year ${y}`}
          />
          {/* Structural debt stacked beneath total assets. */}
          <Area
            type="monotone"
            dataKey="debt"
            stackId="wealth"
            stroke="#a855f7"
            fill="url(#debtFill)"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="assets"
            stackId="wealth"
            stroke="#22c55e"
            fill="url(#assetFill)"
            isAnimationActive={false}
          />
          {/* Solid = this scenario's net worth. */}
          <Line
            type="monotone"
            dataKey="net"
            stroke="#e5e7eb"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          {/* Dashed = Base Plan net worth for divergence (PRD 5.2). */}
          {compare && (
            <Line
              type="monotone"
              dataKey="baseNet"
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

export default memo(MacroChart)
