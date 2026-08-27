import { useMemo, useState } from 'react'

/**
 * Collapsible JSON inspector: type badges, value previews, copy-as-path,
 * and a search box that filters to matching subtrees.
 */

type Json = null | boolean | number | string | Json[] | { [key: string]: Json }

const NODE_CAP = 20_000

function countNodes(value: Json, budget: number): number {
  if (budget <= 0) return 0
  if (Array.isArray(value)) {
    let n = 1
    for (const item of value) {
      n += countNodes(item, budget - n)
      if (n >= budget) return n
    }
    return n
  }
  if (value !== null && typeof value === 'object') {
    let n = 1
    for (const item of Object.values(value)) {
      n += countNodes(item, budget - n)
      if (n >= budget) return n
    }
    return n
  }
  return 1
}

function typeOf(value: Json): string {
  if (value === null) return 'null'
  if (Array.isArray(value)) return `array·${value.length}`
  return typeof value === 'object' ? `object·${Object.keys(value).length}` : typeof value
}

function matches(value: Json, key: string, term: string): boolean {
  if (key.toLowerCase().includes(term)) return true
  if (Array.isArray(value)) return value.some((v, i) => matches(v, String(i), term))
  if (value !== null && typeof value === 'object') {
    return Object.entries(value).some(([k, v]) => matches(v, k, term))
  }
  return String(value).toLowerCase().includes(term)
}

export function JsonTree({ data }: { data: unknown }): React.JSX.Element {
  const [search, setSearch] = useState('')
  const term = search.trim().toLowerCase()
  const tooLarge = useMemo(() => countNodes(data as Json, NODE_CAP) >= NODE_CAP, [data])

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-none items-center gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search keys and values…"
          className="w-64 rounded-md border border-slate-300 bg-slate-50 px-2.5 py-1 text-xs outline-none focus:border-sky-500 dark:border-slate-700 dark:bg-[#0b0f14]"
        />
        {tooLarge && (
          <span className="text-[11px] text-amber-600 dark:text-amber-400">
            Large document — full virtualization lands in 5.12; deep nodes start collapsed.
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3 font-mono text-xs leading-relaxed">
        <Node name="root" value={data as Json} path="$" depth={0} term={term} />
      </div>
    </div>
  )
}

function Node({
  name,
  value,
  path,
  depth,
  term
}: {
  name: string
  value: Json
  path: string
  depth: number
  term: string
}): React.JSX.Element | null {
  const isContainer = value !== null && typeof value === 'object'
  const [open, setOpen] = useState(depth < 2)

  if (term && !matches(value, name, term)) return null
  const expanded = term ? true : open

  const copy = (e: React.MouseEvent): void => {
    e.stopPropagation()
    void navigator.clipboard.writeText(path)
  }

  return (
    <div style={{ paddingLeft: depth === 0 ? 0 : 14 }}>
      <div
        onClick={() => isContainer && setOpen(!open)}
        className={`group flex items-center gap-2 rounded px-1 py-0.5 ${
          isContainer ? 'cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800/60' : ''
        }`}
      >
        <span className="w-3 text-slate-400">{isContainer ? (expanded ? '▾' : '▸') : ''}</span>
        <span className="text-sky-700 dark:text-sky-300">{name}</span>
        <span className="rounded bg-slate-100 px-1 py-px text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
          {typeOf(value)}
        </span>
        {!isContainer && (
          <span
            className={
              typeof value === 'string'
                ? 'text-emerald-700 dark:text-emerald-300'
                : 'text-amber-700 dark:text-amber-300'
            }
          >
            {typeof value === 'string' ? JSON.stringify(value) : String(value)}
          </span>
        )}
        <button
          onClick={copy}
          className="hidden rounded border border-slate-300 px-1 text-[10px] text-slate-400 hover:text-sky-500 group-hover:inline dark:border-slate-600"
          title={`Copy path ${path}`}
        >
          path
        </button>
      </div>
      {isContainer &&
        expanded &&
        (Array.isArray(value)
          ? value.map((item, i) => (
              <Node
                key={i}
                name={String(i)}
                value={item}
                path={`${path}[${i}]`}
                depth={depth + 1}
                term={term}
              />
            ))
          : Object.entries(value).map(([k, v]) => (
              <Node
                key={k}
                name={k}
                value={v}
                path={`${path}.${k}`}
                depth={depth + 1}
                term={term}
              />
            )))}
    </div>
  )
}
