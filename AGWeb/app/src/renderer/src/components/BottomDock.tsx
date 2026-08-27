import { useState } from 'react'
import { useShellStore } from '@/store'

type DockView = 'terminal' | 'logs'

export function BottomDock(): React.JSX.Element {
  const toggleDock = useShellStore((s) => s.toggleDock)
  const [view, setView] = useState<DockView>('terminal')

  return (
    <div className="flex h-56 shrink-0 flex-col border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0e1420]">
      <div className="flex items-center border-b border-slate-200 px-2 dark:border-slate-800">
        {(['terminal', 'logs'] as DockView[]).map((id) => (
          <button
            key={id}
            onClick={() => setView(id)}
            className={`px-3 py-1.5 text-xs font-semibold uppercase tracking-wide ${
              view === id
                ? 'border-b-2 border-sky-500 text-sky-600 dark:text-sky-400'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            {id}
          </button>
        ))}
        <button
          onClick={toggleDock}
          className="ml-auto rounded px-2 py-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          aria-label="Close dock"
        >
          ×
        </button>
      </div>
      <div className="flex-1 overflow-auto p-3 font-mono text-xs text-slate-500">
        {view === 'terminal'
          ? 'Integrated terminal (node-pty + xterm.js) lands in Phase 3.'
          : 'Agent activity logs land in Phase 6.'}
      </div>
    </div>
  )
}
