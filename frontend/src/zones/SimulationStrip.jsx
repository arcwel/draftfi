import { useState } from 'react'
import { useStore } from '../store/useStore'
import MilestoneModal from '../components/MilestoneModal'
import ScenarioInput from '../components/ScenarioInput'

const money = (n) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n || 0)

// Zone 2: interactive simulation parameter strip (PRD 4.2).
export default function SimulationStrip() {
  const parameters = useStore((s) => s.parameters)
  const setParam = useStore((s) => s.setParam)
  const milestones = useStore((s) => s.milestones)
  const addMilestone = useStore((s) => s.addMilestone)
  const updateMilestone = useStore((s) => s.updateMilestone)
  const removeMilestone = useStore((s) => s.removeMilestone)

  const [modal, setModal] = useState(null) // {index?} | null

  const adj = parameters.income_adjustment_pct

  return (
    <div className="flex flex-wrap items-center gap-4 px-4 py-2.5">
      {/* Income slider */}
      <div className="min-w-[240px] flex-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-400">Income Adjustment</span>
          <span
            className={`font-semibold ${adj > 0 ? 'text-emerald-400' : adj < 0 ? 'text-rose-400' : 'text-gray-300'}`}
          >
            {adj > 0 ? '+' : ''}
            {adj}%
          </span>
        </div>
        <input
          type="range"
          min="-30"
          max="30"
          step="1"
          value={adj}
          onChange={(e) =>
            setParam('income_adjustment_pct', Number(e.target.value))
          }
          className="mt-1 w-full"
        />
        <div className="flex justify-between text-[10px] text-gray-600">
          <span>-30%</span>
          <span>+30%</span>
        </div>
      </div>

      {/* Manual financial inputs — leave income/spending on "Auto" to derive
          them from imported transactions instead. */}
      <ParamChip
        label="Income/mo"
        value={parameters.monthly_inflow}
        onChange={(v) => setParam('monthly_inflow', v)}
        format={money}
        allowAuto
      />
      <ParamChip
        label="Spending/mo"
        value={parameters.monthly_outflow}
        onChange={(v) => setParam('monthly_outflow', v)}
        format={money}
        allowAuto
      />
      <ParamChip
        label="Assets"
        value={parameters.starting_assets}
        onChange={(v) => setParam('starting_assets', v)}
        format={money}
      />
      <ParamChip
        label="Debt"
        value={parameters.starting_debt}
        onChange={(v) => setParam('starting_debt', v)}
        format={money}
      />
      <ParamChip
        label="Cash"
        value={parameters.starting_cash}
        onChange={(v) => setParam('starting_cash', v)}
        format={money}
      />
      <ParamChip
        label="Safety floor"
        value={parameters.safety_floor}
        onChange={(v) => setParam('safety_floor', v)}
        format={money}
      />

      {/* Milestones */}
      <div className="flex items-center gap-2">
        {milestones.map((m, i) => (
          <button
            key={i}
            onClick={() => setModal({ index: i })}
            className="group flex items-center gap-1 rounded-full border border-edge bg-panel px-2.5 py-1 text-xs text-gray-300 hover:border-sky-500"
            title={`Edit ${m.label}`}
          >
            <span className="truncate max-w-[120px]">{m.label}</span>
            <span className="text-gray-500">m{m.target_month}</span>
            <span
              onClick={(e) => {
                e.stopPropagation()
                removeMilestone(i)
              }}
              className="ml-1 text-gray-600 group-hover:text-rose-400"
            >
              ✕
            </span>
          </button>
        ))}
        <button
          onClick={() => setModal({})}
          className="rounded-full bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-500"
        >
          + Milestone
        </button>
      </div>

      {/* Full-width natural-language scenario row */}
      <div className="w-full basis-full">
        <ScenarioInput />
      </div>

      {modal && (
        <MilestoneModal
          initial={modal.index != null ? milestones[modal.index] : null}
          onClose={() => setModal(null)}
          onSave={(m) => {
            if (modal.index != null) updateMilestone(modal.index, m)
            else addMilestone(m)
            setModal(null)
          }}
        />
      )}
    </div>
  )
}

function ParamChip({ label, value, onChange, format, allowAuto = false }) {
  const [editing, setEditing] = useState(false)
  const isAuto = allowAuto && (value === null || value === undefined)
  return editing ? (
    <input
      autoFocus
      type="number"
      defaultValue={isAuto ? '' : value}
      placeholder={allowAuto ? 'auto' : ''}
      onBlur={(e) => {
        const raw = e.target.value.trim()
        onChange(raw === '' && allowAuto ? null : Number(raw))
        setEditing(false)
      }}
      onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
      className="w-28 rounded-md border border-sky-500 bg-ink px-2 py-1 text-xs text-gray-100 focus:outline-none"
    />
  ) : (
    <button
      onClick={() => setEditing(true)}
      className="rounded-md border border-edge bg-panel px-2.5 py-1 text-xs"
      title={allowAuto ? 'Blank = derive from imported transactions' : undefined}
    >
      <span className="text-gray-500">{label}: </span>
      <span className={`font-medium ${isAuto ? 'text-gray-500' : 'text-gray-200'}`}>
        {isAuto ? 'Auto' : format(value)}
      </span>
    </button>
  )
}
