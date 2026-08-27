import { useState } from 'react'
import type { DragEvent } from 'react'
import {
  useShellStore,
  type BlockGroup,
  type BlockInstance,
  type DeckZone,
  type DropTarget
} from '@/store'
import { BlockTypeIcon, CloseIcon, GripIcon, MinusIcon, PopOutIcon } from '@/components/icons'
import { BlockContent } from '@/components/BlockContent'

/**
 * The Dev Deck: docked zones of tabbed block groups plus the rail.
 * Drag a tab to move one block; drag a group's grip to move the stack.
 * Drop on a header = stack into that group; on a group's body = insert
 * before it; on a zone's empty space = append to that zone.
 */

const DRAG_MIME = 'application/x-agweb-drag'

interface DragPayload {
  kind: 'block' | 'group'
  id: string
}

function startDrag(event: DragEvent, payload: DragPayload): void {
  event.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload))
  event.dataTransfer.effectAllowed = 'move'
}

function readDrag(event: DragEvent): DragPayload | null {
  try {
    const raw = event.dataTransfer.getData(DRAG_MIME)
    return raw ? (JSON.parse(raw) as DragPayload) : null
  } catch {
    return null
  }
}

function useDropZone(onDrop: (payload: DragPayload) => void): {
  over: boolean
  handlers: {
    onDragOver: (e: DragEvent) => void
    onDragLeave: (e: DragEvent) => void
    onDrop: (e: DragEvent) => void
  }
} {
  const [over, setOver] = useState(false)
  return {
    over,
    handlers: {
      onDragOver: (e) => {
        if (!e.dataTransfer.types.includes(DRAG_MIME)) return
        e.preventDefault()
        e.stopPropagation()
        e.dataTransfer.dropEffect = 'move'
        setOver(true)
      },
      onDragLeave: () => setOver(false),
      onDrop: (e) => {
        e.preventDefault()
        e.stopPropagation()
        setOver(false)
        const payload = readDrag(e)
        if (payload) onDrop(payload)
      }
    }
  }
}

function dropTo(payload: DragPayload, target: DropTarget): void {
  const { moveBlock, moveGroup } = useShellStore.getState()
  if (payload.kind === 'block') moveBlock(payload.id, target)
  else moveGroup(payload.id, target)
}

export function Deck(): React.JSX.Element {
  const groups = useShellStore((s) => s.groups)
  const right = groups.filter((g) => g.zone === 'right')
  const bottom = groups.filter((g) => g.zone === 'bottom')

  return (
    <>
      <ZoneView zone="right" className="deck-col" groups={right} />
      <ZoneView zone="bottom" className="deck-dock" groups={bottom} />
      <Rail />
    </>
  )
}

function ZoneView({
  zone,
  className,
  groups
}: {
  zone: DeckZone
  className: string
  groups: BlockGroup[]
}): React.JSX.Element {
  const { over, handlers } = useDropZone((payload) => dropTo(payload, { kind: 'zone', zone }))
  return (
    <div
      className={`${className} ${over ? 'rounded-xl ring-2 ring-sky-500/50' : ''}`}
      {...handlers}
    >
      {groups.map((group, i) => (
        <GroupView
          key={group.id}
          group={group}
          grow={zone === 'right' || i === 0}
          fixedWidth={zone === 'bottom' && i !== 0 ? 330 : undefined}
        />
      ))}
    </div>
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
  const { activateBlock, addBlockToGroup, closeBlock, sendToRail } = useShellStore()
  const members = group.blockIds.map((id) => blocks[id]).filter(Boolean) as BlockInstance[]
  const active = blocks[group.activeBlockId] ?? members[0]

  const header = useDropZone((payload) => dropTo(payload, { kind: 'stack', groupId: group.id }))
  const body = useDropZone((payload) => dropTo(payload, { kind: 'before', groupId: group.id }))

  return (
    <div
      className={`flex min-h-0 flex-col overflow-hidden rounded-[10px] border bg-white dark:bg-[#0e1420] ${
        body.over
          ? 'border-sky-500 ring-2 ring-sky-500/40'
          : 'border-slate-200 dark:border-slate-800'
      }`}
      style={{
        flex: grow ? 1 : undefined,
        width: fixedWidth,
        flexShrink: fixedWidth ? 0 : undefined
      }}
      {...body.handlers}
    >
      <div
        data-deck-header={group.id}
        className={`flex h-[34px] flex-none items-center gap-1 border-b px-2.5 ${
          header.over ? 'border-sky-500 bg-sky-500/10' : 'border-slate-200 dark:border-slate-800'
        }`}
        {...header.handlers}
      >
        <span
          draggable
          onDragStart={(e) => startDrag(e, { kind: 'group', id: group.id })}
          className="mr-1 shrink-0 cursor-grab text-slate-400 dark:text-slate-600"
          title="Drag to move this stack"
        >
          <GripIcon />
        </span>
        {members.map((block) => (
          <button
            key={block.id}
            draggable
            onDragStart={(e) => startDrag(e, { kind: 'block', id: block.id })}
            onClick={() => activateBlock(group.id, block.id)}
            className={`flex h-full cursor-grab items-center px-2.5 text-[11px] font-bold uppercase tracking-wider ${
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
            title="Float (arrives with detached mode)"
          >
            <PopOutIcon />
          </button>
          {active && (
            <>
              <button
                onClick={() => sendToRail(active.id)}
                className="rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label={`Send ${active.title} to rail`}
              >
                <MinusIcon />
              </button>
              <button
                onClick={() => closeBlock(active.id)}
                className="rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label={`Close ${active.title}`}
              >
                <CloseIcon />
              </button>
            </>
          )}
        </div>
      </div>
      <div className="min-h-0 flex-1">{active && <BlockContent block={active} />}</div>
    </div>
  )
}

function Rail(): React.JSX.Element | null {
  const rail = useShellStore((s) => s.rail)
  const blocks = useShellStore((s) => s.blocks)
  const restoreFromRail = useShellStore((s) => s.restoreFromRail)

  if (rail.length === 0) return null
  return (
    <div className="deck-rail">
      {rail.map((entry) => {
        const block = blocks[entry.blockId]
        if (!block) return null
        return (
          <button
            key={entry.blockId}
            onClick={() => restoreFromRail(entry.blockId)}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-sky-500 hover:text-sky-500 dark:border-slate-800 dark:bg-[#0e1420] dark:text-slate-400"
            aria-label={`Restore ${block.title}`}
            title={block.title}
          >
            <BlockTypeIcon type={block.type} />
          </button>
        )
      })}
    </div>
  )
}
