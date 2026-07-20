import { useState } from 'react'
import { useStore } from '../store/useStore'
import { api } from '../lib/api'

const TONE = {
  warn: 'text-rose-300',
  good: 'text-emerald-300',
  up: 'text-emerald-300',
  down: 'text-rose-300',
}
const ICON = { warn: '▲', good: '▼', up: '▲', down: '▼' }

// A4: heuristic month-over-month insights, with an opt-in LLM narrative. The
// list is deterministic and always shown; the narrative is generated on demand
// so nothing waits on (or requires) a provider.
export default function InsightsCard() {
  const insights = useStore((s) => s.insights)
  const llmOnline = useStore((s) => s.llm.available)
  const [narrative, setNarrative] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  if (!insights || insights.length === 0) return null

  async function summarize() {
    setLoading(true)
    setError(null)
    try {
      const res = await api.insightsNarrative()
      setNarrative(res.narrative)
    } catch (e) {
      setError(e.message || 'Could not generate a summary')
    } finally {
      setLoading(false)
    }
  }

  const month = insights[0]?.month

  return (
    <div className="rounded-xl border border-edge bg-panel/60 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">
          Insights
          {month && (
            <span className="ml-2 text-[11px] font-normal text-gray-500">{month}</span>
          )}
        </h3>
        {llmOnline && (
          <button
            onClick={summarize}
            disabled={loading}
            className="rounded-md border border-edge px-2 py-0.5 text-[11px] text-sky-300 hover:border-sky-500 disabled:opacity-50"
          >
            {loading ? 'Summarizing…' : '✨ Summarize'}
          </button>
        )}
      </div>

      {narrative && (
        <p className="mb-2 rounded-lg border border-sky-900 bg-sky-950/30 p-2 text-xs text-gray-200">
          {narrative}
        </p>
      )}
      {error && <p className="mb-2 text-[11px] text-amber-400">{error}</p>}

      <ul className="space-y-1">
        {insights.map((it, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-gray-300">
            <span className={`mt-0.5 ${TONE[it.kind] || 'text-gray-400'}`}>
              {ICON[it.kind] || '•'}
            </span>
            <span>{it.text}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
