import { afterEach, describe, expect, it } from 'vitest'
import { amount, getFormat, money, setFormat, signed } from './format'

afterEach(() => setFormat({ currency: 'USD', locale: 'en-US' }))

describe('format (G4)', () => {
  it('formats whole-dollar amounts with no cents', () => {
    expect(money(1234.56)).toBe('$1,235')
    expect(money(0)).toBe('$0')
    expect(money(null)).toBe('$0')
  })

  it('formats amounts with minor units', () => {
    expect(amount(59)).toBe('$59.00')
    expect(amount(4.2)).toBe('$4.20')
  })

  it('prefixes signed amounts', () => {
    expect(signed(1200)).toBe('+$1,200')
    expect(signed(-300)).toBe('−$300')
  })

  it('switches currency + locale globally', () => {
    setFormat({ currency: 'EUR', locale: 'de-DE' })
    expect(getFormat()).toEqual({ currency: 'EUR', locale: 'de-DE' })
    // de-DE euro formatting uses a trailing symbol.
    expect(money(1000)).toContain('€')
  })

  it('falls back to USD when the currency code is invalid', () => {
    setFormat({ currency: 'NOTREAL' })
    expect(money(50)).toBe('$50')
  })
})
