import type { BlockInstance } from '@/store'
import { EditorBlock } from '@/components/EditorBlock'
import { TerminalBlock } from '@/components/TerminalBlock'
import { FilesTree } from '@/components/FilesTree'
import { SearchBlock } from '@/components/SearchBlock'
import { AgentsBlock, LogsBlock } from '@/components/AgentsBlock'

/** Content for each block type. */
export function BlockContent({ block }: { block: BlockInstance }): React.JSX.Element {
  switch (block.type) {
    case 'files':
      return <FilesTree />
    case 'terminal':
      return <TerminalBlock id={block.id} />
    case 'editor':
      return <EditorBlock />
    case 'search':
      return <SearchBlock />
    case 'agents':
      return <AgentsBlock />
    case 'logs':
      return <LogsBlock />
  }
}
