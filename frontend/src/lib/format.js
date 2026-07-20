// Shared currency/number formatting (G4). One place owns the currency + locale
// so the whole UI switches together instead of hardcoding USD/en-US per file.

let _currency = 'USD'
let _locale = 'en-US'

// Called once at startup (and on change) from the store's loaded preferences.
export function setFormat({ currency, locale } = {}) {
  if (currency) _currency = currency
  if (locale) _locale = locale
}

export function getFormat() {
  return { currency: _currency, locale: _locale }
}

function format(value, fractionDigits) {
  const v = value || 0
  try {
    return new Intl.NumberFormat(_locale, {
      style: 'currency',
      currency: _currency,
      maximumFractionDigits: fractionDigits,
      minimumFractionDigits: fractionDigits,
    }).format(v)
  } catch {
    // Invalid locale/currency — never let formatting crash the UI.
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: fractionDigits,
      minimumFractionDigits: fractionDigits,
    }).format(v)
  }
}

// Whole-currency amounts (charts, budgets, totals).
export const money = (n) => format(n, 0)

// With minor units (individual transactions, splits).
export const amount = (n) => format(n, 2)

// Signed whole-currency amount, e.g. "+$1,200" / "−$300".
export const signed = (n) => `${n >= 0 ? '+' : '−'}${money(Math.abs(n))}`
