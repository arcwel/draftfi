import { useStore } from '../store/useStore'
import RunwayChart from '../components/RunwayChart'
import MacroChart from '../components/MacroChart'
import BudgetPanel from '../components/BudgetPanel'

const HORIZONS = [12, 24, 36, 48, 60, 72]

// Zone 3: visual simulation grid (PRD 4, 5).
export default function Charts() {
  const series = useStore((s) => s.series)
  const compare = useStore((s) => s.compare)
  const runwayMonths = useStore((s) => s.parameters.runway_months)
  const setParam = useStore((s) => s.setParam)

  return (
    <div className="space-y-3 p-4">
      <BudgetPanel />

      <div className="rounded-xl border border-edge bg-panel/60 p-3">
        <div className="mb-1 flex justify-end gap-1">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => setParam('runway_months', h)}
              className={`rounded px-2 py-0.5 text-[11px] ${
                runwayMonths === h
                  ? 'bg-sky-600 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {h}m
            </button>
          ))}
        </div>
        <RunwayChart series={series} compare={compare} />
      </div>

      <div className="rounded-xl border border-edge bg-panel/60 p-3">
        <MacroChart series={series} compare={compare} />
      </div>
    </div>
  )
}
