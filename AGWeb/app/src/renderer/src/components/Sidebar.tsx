import { useEffect, useState } from 'react'
import type { RecentProject } from '@shared/ipc'
import { useShellStore, type SidebarView } from '@/store'

const VIEWS: { id: SidebarView; label: string }[] = [
  { id: 'projects', label: 'Projects' },
  { id: 'agents', label: 'Agents' }
]

export function Sidebar(): React.JSX.Element {
  const { sidebarView, setSidebarView, workspace, setWorkspace, openTab } = useShellStore()
  const [recent, setRecent] = useState<RecentProject[]>([])

  useEffect(() => {
    void window.agweb.getRecentProjects().then(setRecent)
  }, [workspace])

  const openFolder = async (): Promise<void> => {
    const ws = await window.agweb.openWorkspace()
    if (ws) setWorkspace(ws)
  }

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0e1420]">
      <div className="flex border-b border-slate-200 dark:border-slate-800">
        {VIEWS.map((view) => (
          <button
            key={view.id}
            onClick={() => setSidebarView(view.id)}
            className={`flex-1 px-3 py-2 text-xs font-semibold uppercase tracking-wide ${
              sidebarView === view.id
                ? 'border-b-2 border-sky-500 text-sky-600 dark:text-sky-400'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            {view.label}
          </button>
        ))}
      </div>

      {sidebarView === 'projects' && (
        <div className="flex min-h-0 flex-1 flex-col p-3">
          <button
            onClick={() => void openFolder()}
            className="mb-3 rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500"
          >
            Open Project Folder…
          </button>
          {workspace && (
            <div className="mb-3 rounded-md border border-slate-200 p-2 text-sm dark:border-slate-700">
              <div className="font-medium">{workspace.name}</div>
              <div className="truncate text-xs text-slate-500" title={workspace.path}>
                {workspace.path}
              </div>
            </div>
          )}
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Recent
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {recent.length === 0 && (
              <div className="py-2 text-xs text-slate-500">No recent projects yet.</div>
            )}
            {recent.map((project) => (
              <button
                key={project.path}
                onClick={() => void window.agweb.openWorkspacePath(project.path)}
                className="block w-full truncate rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
                title={project.path}
              >
                {project.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {sidebarView === 'agents' && (
        <div className="flex flex-1 flex-col items-start gap-2 p-3 text-sm text-slate-500">
          <p>No agents running.</p>
          <button
            onClick={() => openTab('mission-control')}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Open Mission Control
          </button>
          <p className="text-xs">Agent orchestration lands in Phase 6.</p>
        </div>
      )}
    </aside>
  )
}
