import { useEffect } from 'react'
import { useStore } from './store/useStore'
import Sidebar from './zones/Sidebar'
import SimulationStrip from './zones/SimulationStrip'
import Charts from './zones/Charts'
import Ledger from './zones/Ledger'
import SyncButton from './components/SyncButton'
import UpdateBanner from './components/UpdateBanner'
import LockScreen from './components/LockScreen'
import iconUrl from './assets/DraftFi_Icon.png'

export default function App() {
  const boot = useStore((s) => s.boot)
  const pollLlm = useStore((s) => s.pollLlm)
  const booted = useStore((s) => s.booted)
  const locked = useStore((s) => s.security.locked)
  // G4: remount the workspace when the currency changes so every money value
  // re-renders in the new currency (not just the data-driven views).
  const currency = useStore((s) => s.preferences.currency)

  useEffect(() => {
    boot()
    // Keep the LLM status pill live. Every poll is a real request against the
    // provider's quota for cloud backends, so keep it infrequent (the backend
    // also caches the verdict) rather than hammering it every few seconds.
    const id = setInterval(pollLlm, 60000)
    return () => clearInterval(id)
  }, [boot, pollLlm])

  // G2: gate the whole UI behind the passcode until unlocked.
  if (!booted) return <div className="min-h-screen bg-ink" />
  if (locked) return <LockScreen />

  return (
    // Natural page scroll on small screens; fixed-viewport dashboard at lg+.
    <div className="flex min-h-screen flex-col bg-ink text-gray-200 lg:h-screen lg:overflow-hidden">
      <header className="flex items-center justify-between border-b border-edge px-4 py-2">
        <div className="flex items-center gap-2">
          <img
            src={iconUrl}
            alt="DraftFi logo"
            className="h-7 w-7 shrink-0"
          />
          <span className="text-lg font-semibold tracking-tight text-white">
            DraftFi
          </span>
          <span className="hidden text-xs text-gray-500 sm:inline">
            local-first financial sandbox · BYO-LLM
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-[11px] text-gray-600 sm:inline">
            all data stays on this machine
          </span>
          <UpdateBanner />
          <SyncButton />
        </div>
      </header>

      {/* Four-zone responsive workspace (PRD §4). Keyed on currency so a
          currency change remounts and reformats the entire tree. */}
      <div
        key={currency}
        className="grid grid-cols-1 lg:min-h-0 lg:flex-1 lg:grid-cols-[280px_minmax(0,1fr)] lg:overflow-hidden"
      >
        {/* Zone 1 */}
        <aside className="border-b border-edge lg:border-b-0 lg:border-r lg:overflow-y-auto">
          <Sidebar />
        </aside>

        <main className="flex flex-col lg:grid lg:min-h-0 lg:grid-rows-[auto_minmax(0,1fr)_auto] lg:overflow-hidden">
          {/* Zone 2 */}
          <div className="border-b border-edge">
            <SimulationStrip />
          </div>
          {/* Zone 3 */}
          <div className="min-h-[460px] lg:min-h-0 lg:overflow-y-auto">
            <Charts />
          </div>
          {/* Zone 4 */}
          <div className="border-t border-edge lg:max-h-[38vh] lg:overflow-hidden">
            <Ledger />
          </div>
        </main>
      </div>
    </div>
  )
}
