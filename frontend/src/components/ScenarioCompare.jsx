import { money, signed } from '../lib/format'
import { useMemo } from 'react'
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useStore } from '../store/useStore'

// Distinct line colors; base always uses the first (slate) slot.
const COLORS = ['#94a3b8', '#38bdf8', '#a855f7', '#f59e0b', '#22c55e', '#f43f5e']

// E4: overlay the Base Plan plus any selected branches, with a delta table
// measuring each scenario against the base at 12 / 36 / 72 months.
export default function ScenarioCompare() {
  const branches = useStore((s) => s.branches)
  const compareBranchIds = useStore((s) => s.compareBranchIds)
  const toggleCompareBranch = useStore((s) => s.toggleCompareBranch)
  const scenarioCompare = useStore((s) => s.scenarioCompare)

  const sandbox = branches.filter((b) => !b.is_base)

  // Combined net-worth-by-year rows keyed by branch id for the overlay chart.
  const chartData = useMemo(() => {
    if (!scenarioCompare) return []
    const byYear = {}
    for (const sc of scenarioCompare.scenarios) {
      for (const p of sc.series.macro) {
        byYear[p.year] ??= { year: p.year }
        byYear[p.year][`s${sc.branch_id}`] = p.net_worth
      }
    }
    return Object.values(byYear).sort((a, b) => a.year - b.year)
  }, [scenarioCompare])

  return (
    <div className="rounded-xl border border-edge bg-panel/60 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-white">
          Compare Scenarios
          <span className="ml-2 text-[11px] font-normal text-gray-500">
            net worth vs. Base Plan
          </span>
        </h3>
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {sandbox.length === 0 && (
            <span className="text-[11px] text-gray-600">
              Create a sandbox branch to compare scenarios.
            </span>
          )}
          {sandbox.map((b) => {
            const on = compareBranchIds.includes(b.id)
            return (
              <button
                key={b.id}
                onClick={() => toggleCompareBranch(b.id)}
                className={`rounded-full border px-2.5 py-0.5 text-[11px] ${
                  on
                    ? 'border-sky-500 bg-sky-950/50 text-sky-200'
                    : 'border-edge text-gray-400 hover:border-gray-500'
                }`}
              >
                {on ? '✓ ' : '+ '}
                {b.name}
              </button>
            )
          })}
        </div>
      </div>

      {!scenarioCompare ? (
        <div className="py-6 text-center text-xs text-gray-600">
          Select one or more branches above to overlay them against the Base Plan.
        </div>
      ) : (
        <>
          {/* Legend */}
          <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-gray-400">
            {scenarioCompare.scenarios.map((sc, i) => (
              <span key={sc.branch_id} className="flex items-center gap-1">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: COLORS[i % COLORS.length] }}
                />
                {sc.name}
                {sc.is_base && <span className="text-gray-600"> (base)</span>}
              </span>
            ))}
          </div>

          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={chartData} margin={{ top: 5, right: 8, left: 8, bottom: 0 }}>
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
                formatter={(v, k) => {
                  const sc = scenarioCompare.scenarios.find((s) => `s${s.branch_id}` === k)
                  return [money(v), sc ? sc.name : k]
                }}
                labelFormatter={(y) => `Year ${y}`}
              />
              {scenarioCompare.scenarios.map((sc, i) => (
                <Line
                  key={sc.branch_id}
                  type="monotone"
                  dataKey={`s${sc.branch_id}`}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={sc.is_base ? 1.5 : 2}
                  strokeDasharray={sc.is_base ? '5 4' : undefined}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>

          {/* Delta table: net worth (and Δ vs base) at each horizon. */}
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead>
                <tr className="text-gray-500">
                  <th className="py-1 pr-2 font-medium">Horizon</th>
                  {scenarioCompare.scenarios.map((sc) => (
                    <th key={sc.branch_id} className="px-2 py-1 font-medium">
                      {sc.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scenarioCompare.deltas.map((row) => (
                  <tr key={row.month} className="border-t border-edge/60">
                    <td className="py-1 pr-2 text-gray-400">{row.month}m</td>
                    {row.cells.map((c) => (
                      <td key={c.branch_id} className="px-2 py-1">
                        <div className="text-gray-200">
                          {c.net_worth != null ? money(c.net_worth) : '—'}
                          {c.net_delta != null && (
                            <span
                              className={`ml-1 ${
                                c.net_delta >= 0 ? 'text-emerald-400' : 'text-rose-400'
                              }`}
                            >
                              {signed(c.net_delta)}
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-gray-600">
                          cash {c.cash != null ? money(c.cash) : '—'}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
