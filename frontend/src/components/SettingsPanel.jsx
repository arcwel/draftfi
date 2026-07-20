import { useEffect, useState } from 'react'
import { useStore } from '../store/useStore'

// Currency + matching locale presets (G4). Pairing them avoids invalid combos
// and keeps the UI to a single choice.
const PRESETS = [
  { label: 'US Dollar', currency: 'USD', locale: 'en-US' },
  { label: 'Euro', currency: 'EUR', locale: 'de-DE' },
  { label: 'British Pound', currency: 'GBP', locale: 'en-GB' },
  { label: 'Canadian Dollar', currency: 'CAD', locale: 'en-CA' },
  { label: 'Australian Dollar', currency: 'AUD', locale: 'en-AU' },
  { label: 'Japanese Yen', currency: 'JPY', locale: 'ja-JP' },
  { label: 'Swiss Franc', currency: 'CHF', locale: 'de-CH' },
  { label: 'Indian Rupee', currency: 'INR', locale: 'en-IN' },
]

const inputCls =
  'w-full rounded-md border border-edge bg-ink px-2 py-1 text-xs text-gray-100 focus:border-sky-500 focus:outline-none'

export default function SettingsPanel() {
  const prefs = useStore((s) => s.preferences)
  const updatePreferences = useStore((s) => s.updatePreferences)
  const security = useStore((s) => s.security)
  const setPasscode = useStore((s) => s.setPasscode)
  const removePasscode = useStore((s) => s.removePasscode)

  const previewTextScale = useStore((s) => s.previewTextScale)

  const [pcNew, setPcNew] = useState('')
  const [pcCurrent, setPcCurrent] = useState('')
  const [pcError, setPcError] = useState(null)
  const [pcFlash, setPcFlash] = useState(null)
  // Local slider value so dragging previews instantly; persisted on release.
  const [scale, setScale] = useState(prefs.text_scale ?? 0)

  useEffect(() => {
    setScale(prefs.text_scale ?? 0)
  }, [prefs.text_scale])

  async function onCurrency(e) {
    const p = PRESETS.find((x) => x.currency === e.target.value)
    if (p) await updatePreferences({ currency: p.currency, locale: p.locale })
  }

  async function onSavePasscode() {
    setPcError(null)
    try {
      await setPasscode(pcNew, security.passcode_set ? pcCurrent : undefined)
      setPcNew('')
      setPcCurrent('')
      setPcFlash(security.passcode_set ? 'Passcode changed ✓' : 'Passcode set ✓')
      setTimeout(() => setPcFlash(null), 2000)
    } catch (err) {
      setPcError(err.message || 'Could not update passcode')
    }
  }

  async function onRemovePasscode() {
    setPcError(null)
    try {
      await removePasscode(pcCurrent)
      setPcCurrent('')
      setPcFlash('Passcode removed')
      setTimeout(() => setPcFlash(null), 2000)
    } catch (err) {
      setPcError(err.message || 'Could not remove passcode')
    }
  }

  const knownCurrency = PRESETS.some((p) => p.currency === prefs.currency)

  return (
    <div className="space-y-3">
      {/* G4: currency / locale */}
      <label className="block">
        <span className="text-[11px] text-gray-500">Currency</span>
        <select
          className={inputCls}
          value={prefs.currency}
          onChange={onCurrency}
        >
          {!knownCurrency && (
            <option value={prefs.currency}>{prefs.currency}</option>
          )}
          {PRESETS.map((p) => (
            <option key={p.currency} value={p.currency}>
              {p.label} ({p.currency})
            </option>
          ))}
        </select>
        <span className="mt-0.5 block text-[10px] text-gray-600">
          Formats every amount as {prefs.currency} · {prefs.locale}
        </span>
      </label>

      {/* Text size: scales the whole UI up to +10pt for readability. */}
      <label className="block">
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-gray-500">Text size</span>
          <span className="text-[10px] text-gray-400">
            {scale > 0 ? `+${scale} pt` : 'Default'}
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="10"
          step="1"
          value={scale}
          onChange={(e) => {
            const v = Number(e.target.value)
            setScale(v)
            previewTextScale(v) // instant feedback while dragging
          }}
          onPointerUp={() => updatePreferences({ text_scale: scale })}
          onKeyUp={() => updatePreferences({ text_scale: scale })}
          className="mt-1 w-full"
        />
        <div className="flex justify-between text-[10px] text-gray-600">
          <span>Default</span>
          <span>+10 pt</span>
        </div>
      </label>

      {/* G2: passcode */}
      <div className="border-t border-edge pt-2">
        <div className="mb-1 flex items-center justify-between">
          <span className="text-[11px] text-gray-500">App passcode</span>
          <span
            className={`text-[10px] ${security.passcode_set ? 'text-emerald-400' : 'text-gray-600'}`}
          >
            {security.passcode_set ? 'On' : 'Off'}
          </span>
        </div>
        {security.passcode_set && (
          <input
            type="password"
            className={`${inputCls} mb-1`}
            value={pcCurrent}
            placeholder="Current passcode"
            onChange={(e) => setPcCurrent(e.target.value)}
          />
        )}
        <input
          type="password"
          className={inputCls}
          value={pcNew}
          placeholder={security.passcode_set ? 'New passcode (min 4)' : 'Set a passcode (min 4)'}
          onChange={(e) => setPcNew(e.target.value)}
        />
        {pcError && <p className="mt-1 text-[10px] text-rose-400">{pcError}</p>}
        {pcFlash && <p className="mt-1 text-[10px] text-emerald-400">{pcFlash}</p>}
        <div className="mt-1.5 flex gap-2">
          <button
            onClick={onSavePasscode}
            disabled={pcNew.length < 4}
            className="flex-1 rounded-md bg-sky-600 py-1 text-[11px] font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {security.passcode_set ? 'Change' : 'Set passcode'}
          </button>
          {security.passcode_set && (
            <button
              onClick={onRemovePasscode}
              disabled={!pcCurrent}
              className="rounded-md border border-edge px-2 py-1 text-[11px] text-gray-400 hover:text-rose-400 disabled:opacity-50"
            >
              Remove
            </button>
          )}
        </div>
        <p className="mt-1 text-[10px] text-gray-600">
          Locks the app on launch until the passcode is entered.
        </p>
      </div>
    </div>
  )
}
