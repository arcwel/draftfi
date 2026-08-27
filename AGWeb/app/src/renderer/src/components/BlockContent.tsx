import { useEffect, useState } from 'react'
import type { RecentProject } from '@shared/ipc'
import { useShellStore, type BlockInstance } from '@/store'

/** Content for each block type. Editor/Terminal are placeholders until
 *  Phase 3 wires Monaco and node-pty; Files and Agents carry real state. */
export function BlockContent({ block }: { block: BlockInstance }): React.JSX.Element {
  switch (block.type) {
    case 'files':
      return <FilesBlock />
    case 'terminal':
      return (
        <div className="h-full p-3 font-mono text-xs leading-relaxed text-slate-500">
          {block.title} — integrated terminal (node-pty + xterm.js) lands in Phase 3.
        </div>
      )
    case 'editor':
      return (
        <div className="flex h-full items-center justify-center p-4 text-sm text-slate-500">
          {block.title} — Monaco editor lands in Phase 3.
        </div>
      )
    case 'agents':
      return (
        <div className="flex h-full flex-col items-start gap-2.5 p-3 text-xs text-slate-500">
          <div>No agents running · plan queue empty</div>
          <button className="rounded-md border border-slate-300 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800">
            New task…
          </button>
          <div className="text-[11px]">Agent orchestration lands in Phase 6.</div>
        </div>
      )
    case 'logs':
      return (
        <div className="h-full p-3 font-mono text-xs text-slate-500">
          Activity logs land with agent orchestration (Phase 6).
        </div>
      )
  }
}

function FilesBlock(): React.JSX.Element {
  const workspace = useShellStore((s) => s.workspace)
  const setWorkspace = useShellStore((s) => s.setWorkspace)
  const [recent, setRecent] = useState<RecentProject[]>([])

  useEffect(() => {
    void window.agweb.getRecentProjects().then(setRecent)
  }, [workspace])

  const openFolder = async (): Promise<void> => {
    const ws = await window.agweb.openWorkspace()
    if (ws) setWorkspace(ws)
  }

  return (
    <div className="flex h-full flex-col gap-2 overflow-y-auto p-3 text-xs">
      <button
        onClick={() => void openFolder()}
        className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
      >
        Open Project Folder…
      </button>
      {workspace ? (
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-700">
          <div className="font-medium text-slate-700 dark:text-slate-200">{workspace.name}</div>
          <div className="truncate text-[11px] text-slate-500" title={workspace.path}>
            {workspace.path}
          </div>
          <div className="mt-1 text-[11px] text-slate-500">File tree lands in Phase 3.</div>
        </div>
      ) : (
        <div className="text-slate-500">No project open.</div>
      )}
      {recent.length > 0 && (
        <>
          <div className="mt-1 font-semibold uppercase tracking-wide text-slate-500">Recent</div>
          {recent.slice(0, 6).map((project) => (
            <button
              key={project.path}
              onClick={() => void window.agweb.openWorkspacePath(project.path)}
              className="truncate rounded px-1.5 py-1 text-left text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              title={project.path}
            >
              {project.name}
            </button>
          ))}
        </>
      )}
    </div>
  )
}
