// Column geometry for the categorization ledger.
//
// The ledger is the one table people actually work in, and raw bank descriptors
// vary wildly in length — a fixed cap either truncates the useful part or wastes
// half the pane. So widths are user-controlled and persisted with the rest of
// the display preferences, which means this module owns two things: the defaults
// and the validation that keeps a stored value sane.

export const LEDGER_COLUMNS = [
  { key: 'date', label: 'Date', width: 96, min: 72 },
  // The widest default: raw descriptors are the reason resizing exists.
  { key: 'raw', label: 'Raw Descriptor', width: 260, min: 120 },
  { key: 'merchant', label: 'Clean Merchant', width: 220, min: 120 },
  { key: 'amount', label: 'Amount', width: 112, min: 88 },
  { key: 'category', label: 'Category', width: 176, min: 120 },
  { key: 'resolution', label: 'Resolution', width: 112, min: 88 },
  { key: 'actions', label: '', width: 92, min: 72 },
]

// Generous but bounded: wide enough for a pathological descriptor, narrow
// enough that a stray drag can't push the table into the megapixels.
export const MAX_COLUMN_WIDTH = 900

const BY_KEY = new Map(LEDGER_COLUMNS.map((c) => [c.key, c]))

export function clampWidth(key, px) {
  const col = BY_KEY.get(key)
  if (!col) return null
  const n = Math.round(Number(px))
  if (!Number.isFinite(n)) return col.width
  return Math.max(col.min, Math.min(MAX_COLUMN_WIDTH, n))
}

export function defaultWidths() {
  return Object.fromEntries(LEDGER_COLUMNS.map((c) => [c.key, c.width]))
}

// Defaults overlaid with whatever was stored. Unknown keys are dropped and bad
// values fall back rather than propagating: a preference written by an older
// build (or hand-edited) must never be able to render an unusable table.
export function mergeWidths(saved) {
  const widths = defaultWidths()
  if (!saved || typeof saved !== 'object') return widths
  for (const [key, value] of Object.entries(saved)) {
    const clamped = clampWidth(key, value)
    if (clamped != null) widths[key] = clamped
  }
  return widths
}

export function totalWidth(widths) {
  return LEDGER_COLUMNS.reduce((sum, c) => sum + (widths[c.key] || c.width), 0)
}
