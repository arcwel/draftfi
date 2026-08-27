import { useShellStore } from '@/store'
import { listShortcuts } from '@/shortcuts'

export function WelcomeView(): React.JSX.Element {
  const setWorkspace = useShellStore((s) => s.setWorkspace)
  const openTab = useShellStore((s) => s.openTab)

  const openFolder = async (): Promise<void> => {
    const ws = await window.agweb.openWorkspace()
    if (ws) setWorkspace(ws)
  }

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col justify-center gap-6 px-8">
      <div>
        <h1 className="text-3xl font-semibold">AGWeb</h1>
        <p className="mt-1 text-slate-500">
          Agent-first workspace: IDE, browser, and Mission Control in one place.
        </p>
      </div>
      <div className="flex gap-3">
        <button
          onClick={() => void openFolder()}
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
        >
          Open Project Folder…
        </button>
        <button
          onClick={() => openTab('mission-control')}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800"
        >
          Mission Control
        </button>
      </div>
      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Keyboard shortcuts
        </h2>
        <ul className="grid grid-cols-2 gap-1 text-sm text-slate-600 dark:text-slate-400">
          {listShortcuts().map((s) => (
            <li key={s.combo}>
              <kbd className="rounded border border-slate-300 bg-slate-100 px-1.5 py-0.5 font-mono text-xs dark:border-slate-600 dark:bg-slate-800">
                {s.combo}
              </kbd>{' '}
              {s.description}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
