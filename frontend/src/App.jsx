import { useEffect } from 'react'
import { useStore } from './store/useStore'
import Sidebar from './zones/Sidebar'
import SimulationStrip from './zones/SimulationStrip'
import Charts from './zones/Charts'
import Ledger from './zones/Ledger'
import SyncButton from './components/SyncButton'
import UpdateBanner from './components/UpdateBanner'
import iconUrl from './assets/DraftFi_Icon.png'

export default function App() {
  const init = useStore((s) => s.init)
  const pollLlm = useStore((s) => s.pollLlm)

  useEffect(() => {
    init()
    // Keep the LLM status pill live.
    const id = setInterval(pollLlm, 8000)
    return () => clearInterval(id)
  }, [init, pollLlm])

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

      {/* Four-zone responsive workspace (PRD §4). */}
      <div className="grid grid-cols-1 lg:min-h-0 lg:flex-1 lg:grid-cols-[280px_minmax(0,1fr)] lg:overflow-hidden">
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
