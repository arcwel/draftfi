import { useState } from 'react'
import { useStore } from '../store/useStore'
import iconUrl from '../assets/DraftFi_Icon.png'

// G2: full-screen passcode gate shown before any data loads. The passcode is
// verified server-side; data endpoints stay refused (423) until it unlocks.
export default function LockScreen() {
  const unlock = useStore((s) => s.unlock)
  const [code, setCode] = useState('')
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!code || busy) return
    setBusy(true)
    setError(false)
    try {
      const ok = await unlock(code)
      if (!ok) {
        setError(true)
        setCode('')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-xs rounded-2xl border border-edge bg-panel p-6 text-center shadow-xl"
      >
        <img src={iconUrl} alt="DraftFi" className="mx-auto mb-3 h-12 w-12" />
        <h1 className="text-lg font-semibold text-white">DraftFi is locked</h1>
        <p className="mt-1 text-xs text-gray-500">
          Enter your passcode to continue.
        </p>
        <input
          autoFocus
          type="password"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Passcode"
          className={`mt-4 w-full rounded-md border bg-ink px-3 py-2 text-center text-sm text-gray-100 focus:outline-none ${
            error ? 'border-rose-500' : 'border-edge focus:border-sky-500'
          }`}
        />
        {error && (
          <p className="mt-2 text-[11px] text-rose-400">Incorrect passcode.</p>
        )}
        <button
          type="submit"
          disabled={busy || !code}
          className="mt-4 w-full rounded-md bg-sky-600 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {busy ? 'Unlocking…' : 'Unlock'}
        </button>
      </form>
    </div>
  )
}
