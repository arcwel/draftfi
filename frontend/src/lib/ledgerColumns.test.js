import { describe, expect, it } from 'vitest'
import {
  LEDGER_COLUMNS,
  MAX_COLUMN_WIDTH,
  clampWidth,
  defaultWidths,
  mergeWidths,
  totalWidth,
} from './ledgerColumns'

describe('ledger column widths', () => {
  it('keeps a column above its minimum so it can never be dragged shut', () => {
    for (const col of LEDGER_COLUMNS) {
      expect(clampWidth(col.key, 0)).toBe(col.min)
      expect(clampWidth(col.key, -500)).toBe(col.min)
    }
  })

  it('caps runaway widths', () => {
    expect(clampWidth('raw', 99999)).toBe(MAX_COLUMN_WIDTH)
  })

  it('rejects unknown columns instead of inventing one', () => {
    expect(clampWidth('nope', 200)).toBeNull()
  })

  it('falls back to the default for a non-numeric stored value', () => {
    const raw = LEDGER_COLUMNS.find((c) => c.key === 'raw')
    expect(clampWidth('raw', 'wide')).toBe(raw.width)
  })

  it('merges stored widths over the defaults', () => {
    const merged = mergeWidths({ raw: 400 })
    expect(merged.raw).toBe(400)
    expect(merged.date).toBe(defaultWidths().date)
  })

  it('ignores keys from another build rather than rendering them', () => {
    const merged = mergeWidths({ raw: 400, legacy_column: 300 })
    expect(merged).not.toHaveProperty('legacy_column')
    expect(Object.keys(merged).sort()).toEqual(
      LEDGER_COLUMNS.map((c) => c.key).sort(),
    )
  })

  it('survives junk where a preferences object was expected', () => {
    for (const junk of [null, undefined, 'nope', 42, []]) {
      expect(mergeWidths(junk)).toEqual(defaultWidths())
    }
  })

  it('clamps stored values, so a bad write cannot render an unusable table', () => {
    expect(mergeWidths({ raw: -10 }).raw).toBe(
      LEDGER_COLUMNS.find((c) => c.key === 'raw').min,
    )
  })

  it('totals the widths for the fixed table layout', () => {
    expect(totalWidth(defaultWidths())).toBe(
      LEDGER_COLUMNS.reduce((n, c) => n + c.width, 0),
    )
  })
})
