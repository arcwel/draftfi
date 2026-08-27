import { useShellStore, type BlockGroup, type BlockInstance } from '@/store'
import { CloseIcon, GripIcon, PopOutIcon } from '@/components/icons'
import { BlockContent } from '@/components/BlockContent'

/**
 * The Dev Deck: docked zones of block groups. Groups are tabbed stacks —
 * every block in a group renders as a tab; `+` opens another instance of
 * the active block's type into the group. Always mounted so the reveal
 * animation can slide the zones in and out (visibility via .revealed).
 */
export function Deck(): React.JSX.Element {
  const groups = useShellStore((s) => s.groups)
  const right = groups.filter((g) => g.zone === 'right')
  const bottom = groups.filter((g) => g.zone === 'bottom')

  return (
    <>
      <div className="deck-col">
        {right.map((group) => (
          <GroupView key={group.id} group={group} grow />
        ))}
      </div>
      <div className="deck-dock">
        {bottom.map((group, i) => (
          <GroupView
            key={group.id}
            group={group}
            grow={i === 0}
            fixedWidth={i !== 0 ? 330 : undefined}
          />
        ))}
      </div>
    </>
  )
}

function GroupView({
  group,
  grow,
  fixedWidth
}: {
  group: BlockGroup
  grow?: boolean
  fixedWidth?: number
}): React.JSX.Element {
  const blocks = useShellStore((s) => s.blocks)
  const { activateBlock, addBlockToGroup, closeBlock } = useShellStore()
  const members = group.blockIds.map((id) => blocks[id]).filter(Boolean) as BlockInstance[]
  const active = blocks[group.activeBlockId] ?? members[0]

  return (
    <div
      className="flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0e1420]"
      style={{
        flex: grow ? 1 : undefined,
        width: fixedWidth,
        flexShrink: fixedWidth ? 0 : undefined
      }}
    >
      <div className="flex h-[34px] flex-none items-center gap-1 border-b border-slate-200 px-2.5 dark:border-slate-800">
        <GripIcon className="mr-1 shrink-0 cursor-grab text-slate-400 dark:text-slate-600" />
        {members.map((block) => (
          <button
            key={block.id}
            onClick={() => activateBlock(group.id, block.id)}
            className={`flex h-full items-center px-2.5 text-[11px] font-bold uppercase tracking-wider ${
              block.id === active?.id
                ? 'border-b-2 border-sky-500 text-slate-700 dark:text-slate-200'
                : 'font-semibold text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300'
            }`}
          >
            {block.title}
          </button>
        ))}
        {active && (
          <button
            onClick={() => addBlockToGroup(group.id, active.type)}
            className="flex h-[22px] w-[22px] items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 dark:text-slate-500 dark:hover:bg-slate-800"
            aria-label={`New ${active.type}`}
          >
            +
          </button>
        )}
        <div className="ml-auto flex items-center gap-1.5 text-slate-400 dark:text-slate-600">
          <button
            className="rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800"
            title="Float (coming soon)"
          >
            <PopOutIcon />
          </button>
          {active && (
            <button
              onClick={() => closeBlock(active.id)}
              className="rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label={`Close ${active.title}`}
            >
              <CloseIcon />
            </button>
          )}
        </div>
      </div>
      <div className="min-h-0 flex-1">{active && <BlockContent block={active} />}</div>
    </div>
  )
}
