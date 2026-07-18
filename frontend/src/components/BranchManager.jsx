import { useState } from 'react'
import { useStore } from '../store/useStore'

// Radio cards for Base vs. Sandbox branches + a Combined Overlay toggle.
// Sandbox branches are renamable and persist to sandbox.db.
export default function BranchManager() {
  const branches = useStore((s) => s.branches)
  const activeBranchId = useStore((s) => s.activeBranchId)
  const overlay = useStore((s) => s.overlay)
  const saveState = useStore((s) => s.branchSaveState)
  const setActiveBranch = useStore((s) => s.setActiveBranch)
  const toggleOverlay = useStore((s) => s.toggleOverlay)
  const createBranch = useStore((s) => s.createBranch)
  const deleteBranch = useStore((s) => s.deleteBranch)
  const renameBranch = useStore((s) => s.renameBranch)
  const [busy, setBusy] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [draftName, setDraftName] = useState('')

  const active = branches.find((b) => b.id === activeBranchId)
  const canOverlay = active && !active.is_base

  async function onBranch() {
    setBusy(true)
    try {
      const n = branches.filter((b) => !b.is_base).length + 1
      await createBranch(`Sandbox ${n}`)
    } finally {
      setBusy(false)
    }
  }

  function startRename(b) {
    setEditingId(b.id)
    setDraftName(b.name)
  }

  async function commitRename(id) {
    await renameBranch(id, draftName)
    setEditingId(null)
  }

  return (
    <div className="space-y-1.5">
      {branches.map((b) => (
        <div
          key={b.id}
          className={`flex items-center gap-2 rounded-lg border px-2.5 py-2 text-sm transition
            ${b.id === activeBranchId ? 'border-sky-500 bg-sky-950/40' : 'border-edge bg-panel hover:border-gray-500'}`}
        >
          <input
            type="radio"
            name="branch"
            className="accent-sky-500"
            checked={b.id === activeBranchId}
            onChange={() => setActiveBranch(b.id)}
          />
          {editingId === b.id ? (
            <input
              autoFocus
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              onBlur={() => commitRename(b.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitRename(b.id)
                if (e.key === 'Escape') setEditingId(null)
              }}
              className="flex-1 rounded border border-sky-500 bg-ink px-1.5 py-0.5 text-sm text-gray-100 focus:outline-none"
            />
          ) : (
            <button
              className="flex-1 truncate text-left"
              onClick={() => setActiveBranch(b.id)}
              onDoubleClick={() => !b.is_base && startRename(b)}
              title={b.is_base ? undefined : 'Double-click to rename'}
            >
              {b.name}
              {b.is_base && (
                <span className="ml-1 text-[10px] uppercase tracking-wide text-gray-500">
                  protected
                </span>
              )}
            </button>
          )}
          {!b.is_base && editingId !== b.id && (
            <>
              <button
                onClick={() => startRename(b)}
                className="text-gray-500 hover:text-sky-300 text-xs"
                title="Rename"
              >
                ✎
              </button>
              <button
                onClick={() => deleteBranch(b.id)}
                className="text-gray-500 hover:text-rose-400 text-xs"
                title="Delete branch"
              >
                ✕
              </button>
            </>
          )}
        </div>
      ))}

      <div className="flex items-center justify-between">
        <button
          onClick={onBranch}
          disabled={busy}
          className="flex-1 rounded-lg border border-edge bg-panel py-1.5 text-xs text-gray-300 hover:border-sky-500 hover:text-sky-300 disabled:opacity-50"
        >
          + Branch from “{active?.name ?? 'Base Plan'}”
        </button>
      </div>

      {/* Persistence indicator — sandbox edits auto-save to the database. */}
      {canOverlay && (
        <div className="text-right text-[10px] text-gray-500">
          {saveState === 'saving'
            ? 'Saving to database…'
            : saveState === 'saved'
              ? 'Saved to database ✓'
              : 'Edits auto-save to database'}
        </div>
      )}

      <label
        className={`mt-1 flex items-center gap-2 text-xs ${canOverlay ? 'text-gray-300' : 'text-gray-600'}`}
      >
        <input
          type="checkbox"
          className="accent-sky-500"
          disabled={!canOverlay}
          checked={overlay && canOverlay}
          onChange={toggleOverlay}
        />
        Combined Overlay (vs. Base Plan)
      </label>
    </div>
  )
}
