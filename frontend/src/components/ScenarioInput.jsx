import { useState } from 'react'
import { useStore } from '../store/useStore'

// Natural-language scenario input (PRD §1): describe a "what-if" in plain
// English and the LLM turns it into milestones + parameter changes.
export default function ScenarioInput() {
  const applyScenarioText = useStore((s) => s.applyScenarioText)
  const parsing = useStore((s) => s.scenarioParsing)
  const note = useStore((s) => s.scenarioNote)
  const llm = useStore((s) => s.llm)
  const [text, setText] = useState('')
  const [error, setError] = useState(null)

  async function submit() {
    const trimmed = text.trim()
    if (!trimmed || parsing) return
    setError(null)
    try {
      await applyScenarioText(trimmed)
      setText('')
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="w-full">
      <div className="flex items-center gap-2">
        <span className="text-sm" title="Describe a scenario in plain English">
          ✨
        </span>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder={
            llm.available
              ? 'Describe a what-if… e.g. "buy a $400k house in 10 months with 20% down"'
              : 'Connect an LLM provider to describe scenarios in plain English'
          }
          disabled={parsing}
          className="flex-1 rounded-md border border-edge bg-ink px-2.5 py-1.5 text-xs text-gray-100 placeholder-gray-600 focus:border-sky-500 focus:outline-none disabled:opacity-60"
        />
        <button
          onClick={submit}
          disabled={parsing || !text.trim()}
          className="flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {parsing && (
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
          )}
          {parsing ? 'Drafting…' : 'Draft it'}
        </button>
      </div>
      {error && <p className="mt-1 text-[11px] text-rose-400">{error}</p>}
      {note && !error && (
        <p className="mt-1 text-[11px] text-sky-300">{note}</p>
      )}
    </div>
  )
}
