// Resolution + category badges (PRD 4.3).
export function ResolutionBadge({ resolution }) {
  const map = {
    cache: { label: 'Cache Hit', cls: 'bg-emerald-950 text-emerald-300 border-emerald-800' },
    override: { label: 'Override', cls: 'bg-blue-950 text-blue-300 border-blue-800' },
    llm: { label: 'LLM Cleaned', cls: 'bg-purple-950 text-purple-300 border-purple-800' },
    manual: { label: 'Manual', cls: 'bg-teal-950 text-teal-300 border-teal-800' },
    uncategorized: {
      label: 'Uncategorized',
      cls: 'bg-gray-800 text-gray-400 border-gray-700',
    },
  }
  const b = map[resolution] || map.uncategorized
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-medium ${b.cls}`}
    >
      {b.label}
    </span>
  )
}

export function CategoryChip({ name, color }) {
  if (!name) return <span className="text-gray-600">—</span>
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ background: color || '#64748b' }}
      />
      {name}
    </span>
  )
}
