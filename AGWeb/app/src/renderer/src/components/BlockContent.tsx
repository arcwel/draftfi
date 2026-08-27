import type { BlockInstance } from '@/store'
import { EditorBlock } from '@/components/EditorBlock'
import { TerminalBlock } from '@/components/TerminalBlock'
import { FilesTree } from '@/components/FilesTree'

/** Content for each block type. Agents/Logs fill in with Phase 6. */
export function BlockContent({ block }: { block: BlockInstance }): React.JSX.Element {
  switch (block.type) {
    case 'files':
      return <FilesTree />
    case 'terminal':
      return <TerminalBlock id={block.id} />
    case 'editor':
      return <EditorBlock />
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
