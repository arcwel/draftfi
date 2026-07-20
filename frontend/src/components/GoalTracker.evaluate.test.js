import { describe, expect, it } from 'vitest'
import { evaluate } from './GoalTracker'

const series = {
  runway: [{ cash: 1000 }, { cash: 1100 }, { cash: 1200 }],
  macro: [{ net_worth: 5000 }, { net_worth: 8000 }],
}

describe('GoalTracker.evaluate (E5)', () => {
  it('marks a cash goal on-track when the projection meets the target', () => {
    const r = evaluate({ kind: 'cash', target_amount: 1000, target_month: 2 }, series)
    expect(r.projected).toBe(1200)
    expect(r.onTrack).toBe(true)
  })

  it('marks a cash goal off-track when short', () => {
    const r = evaluate({ kind: 'cash', target_amount: 5000, target_month: 2 }, series)
    expect(r.onTrack).toBe(false)
  })

  it('reads net worth from the macro series by year', () => {
    const r = evaluate({ kind: 'net_worth', target_amount: 6000, target_month: 12 }, series)
    expect(r.projected).toBe(8000)
    expect(r.onTrack).toBe(true)
  })

  it('handles a missing series safely', () => {
    expect(evaluate({ kind: 'cash', target_amount: 1, target_month: 0 }, null)).toEqual({
      projected: null,
      onTrack: false,
    })
  })
})
