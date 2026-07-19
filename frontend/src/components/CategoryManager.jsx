import { useState } from 'react'
import { useStore } from '../store/useStore'

const inputCls =
  'rounded-md border border-edge bg-ink px-2 py-1 text-xs text-gray-100 focus:border-sky-500 focus:outline-none'

// Create / rename / recolor / merge / delete categories.
export default function CategoryManager({ onClose }) {
  const categories = useStore((s) => s.categories)
  const createCategory = useStore((s) => s.createCategory)
  const updateCategory = useStore((s) => s.updateCategory)
  const deleteCategory = useStore((s) => s.deleteCategory)
  const mergeCategory = useStore((s) => s.mergeCategory)

  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState('#38BDF8')
  const [renamingId, setRenamingId] = useState(null)
  const [draft, setDraft] = useState('')
  const [mergingId, setMergingId] = useState(null)
  const [error, setError] = useState(null)

  async function guard(fn) {
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e.message)
    }
  }

  async function onDelete(cat) {
    const ok = window.confirm(
      `Delete "${cat.name}"?\n\nIts transactions move to Uncategorized.`,
    )
    if (ok) await guard(() => deleteCategory(cat.id))
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-md flex-col rounded-xl border border-edge bg-panel p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-3 text-sm font-semibold text-white">Manage Categories</h3>

        {/* Create */}
        <div className="mb-3 flex items-center gap-2">
          <input
            type="color"
            value={newColor}
            onChange={(e) => setNewColor(e.target.value)}
            className="h-7 w-8 cursor-pointer rounded border border-edge bg-ink"
            title="Color"
          />
          <input
            className={`${inputCls} flex-1`}
            placeholder="New category name…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && newName.trim())
                guard(async () => {
                  await createCategory(newName.trim(), newColor)
                  setNewName('')
                })
            }}
          />
          <button
            onClick={() =>
              newName.trim() &&
              guard(async () => {
                await createCategory(newName.trim(), newColor)
                setNewName('')
              })
            }
            className="rounded-md bg-sky-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-sky-500"
          >
            Add
          </button>
        </div>

        {/* List */}
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
          {categories.map((cat) => {
            const protectedCat = cat.name === 'Uncategorized'
            return (
              <div
                key={cat.id}
                className="flex items-center gap-2 rounded-md px-1.5 py-1 hover:bg-ink/60"
              >
                <input
                  type="color"
                  value={cat.color}
                  disabled={protectedCat}
                  onChange={(e) =>
                    guard(() => updateCategory(cat.id, { color: e.target.value }))
                  }
                  className="h-5 w-6 cursor-pointer rounded border border-edge bg-ink disabled:opacity-40"
                />
                {renamingId === cat.id ? (
                  <input
                    autoFocus
                    className={`${inputCls} flex-1`}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onBlur={() => {
                      if (draft.trim() && draft !== cat.name)
                        guard(() => updateCategory(cat.id, { name: draft.trim() }))
                      setRenamingId(null)
                    }}
                    onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
                  />
                ) : (
                  <button
                    className="flex-1 truncate text-left text-xs text-gray-200"
                    onDoubleClick={() => {
                      if (protectedCat) return
                      setRenamingId(cat.id)
                      setDraft(cat.name)
                    }}
                    title={protectedCat ? 'Protected' : 'Double-click to rename'}
                  >
                    {cat.name}
                    {cat.monthly_budget != null && (
                      <span className="ml-1 text-[10px] text-gray-500">
                        (budget ${cat.monthly_budget})
                      </span>
                    )}
                  </button>
                )}
                {!protectedCat && renamingId !== cat.id && (
                  <>
                    {mergingId === cat.id ? (
                      <select
                        autoFocus
                        className={inputCls}
                        defaultValue=""
                        onBlur={() => setMergingId(null)}
                        onChange={(e) => {
                          const target = Number(e.target.value)
                          setMergingId(null)
                          if (target)
                            guard(() => mergeCategory(cat.id, target))
                        }}
                      >
                        <option value="" disabled>
                          Merge into…
                        </option>
                        {categories
                          .filter((c) => c.id !== cat.id)
                          .map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                      </select>
                    ) : (
                      <button
                        onClick={() => setMergingId(cat.id)}
                        className="text-[10px] text-gray-500 hover:text-sky-300"
                        title="Merge into another category"
                      >
                        merge
                      </button>
                    )}
                    <button
                      onClick={() => onDelete(cat)}
                      className="text-xs text-gray-500 hover:text-rose-400"
                      title="Delete category"
                    >
                      ✕
                    </button>
                  </>
                )}
              </div>
            )
          })}
        </div>

        {error && <p className="mt-2 text-[11px] text-rose-400">{error}</p>}

        <div className="mt-3 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
