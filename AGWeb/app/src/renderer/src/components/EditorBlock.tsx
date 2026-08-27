import { useEffect, useRef, useState } from 'react'
import { ensureModel, monaco } from '@/monaco'
import { useShellStore } from '@/store'
import { canFormat, formatModel } from '@/format'
import { CloseIcon } from '@/components/icons'

/**
 * Monaco-backed editor. Documents are Monaco models keyed by workspace path
 * (shared by every editor instance in this window); the open-tab list and
 * focused document live in the store, synced across windows. ⌘S saves,
 * ⇧⌥F formats (Prettier), and Diff compares the buffer against disk.
 */

/** Workspace-relative path a model was created for (agweb:/<path>). */
const pathOfModel = (model: monaco.editor.ITextModel): string => model.uri.path.replace(/^\//, '')

export function EditorBlock(): React.JSX.Element {
  const editorTabs = useShellStore((s) => s.editorTabs)
  const activePath = useShellStore((s) => s.activeEditorPath)
  const pendingRevealLine = useShellStore((s) => s.pendingRevealLine)
  const dirtyFiles = useShellStore((s) => s.dirtyFiles)
  const theme = useShellStore((s) => s.theme)
  const { openFile, closeEditorTab } = useShellStore()
  const [formatError, setFormatError] = useState<string | null>(null)
  const [diffOpen, setDiffOpen] = useState(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)

  const runFormat = async (): Promise<void> => {
    const model = editorRef.current?.getModel()
    if (!model) return
    const error = await formatModel(pathOfModel(model), model)
    setFormatError(error)
    if (!error) setTimeout(() => setFormatError(null), 1)
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const editor = monaco.editor.create(container, {
      automaticLayout: true,
      fontSize: 13,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      theme: useShellStore.getState().theme === 'dark' ? 'vs-dark' : 'vs'
    })
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      // The path must come from the mounted model, not the active-tab state:
      // during the async model swap after a tab switch they briefly disagree,
      // and writing tab B's path with tab A's model would destroy B on disk.
      const model = editor.getModel()
      if (!model) return
      const path = pathOfModel(model)
      void window.agweb.fs.write(path, model.getValue()).then((result) => {
        if (!result.error) useShellStore.getState().setFileDirty(path, false)
      })
    })
    editor.addCommand(monaco.KeyMod.Shift | monaco.KeyMod.Alt | monaco.KeyCode.KeyF, () => {
      void runFormat()
    })
    editorRef.current = editor
    return () => {
      editorRef.current = null
      editor.dispose()
    }
    // The editor instance is created once; theme updates below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    monaco.editor.setTheme(theme === 'dark' ? 'vs-dark' : 'vs')
  }, [theme])

  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    if (!activePath) {
      editor.setModel(null)
      return
    }
    let cancelled = false
    void ensureModel(activePath).then((model) => {
      if (cancelled || !model || !editorRef.current) return
      editorRef.current.setModel(model)
      const line = useShellStore.getState().pendingRevealLine
      if (line) {
        editorRef.current.revealLineInCenter(line)
        editorRef.current.setPosition({ lineNumber: line, column: 1 })
        useShellStore.getState().clearPendingReveal()
      }
    })
    return () => {
      cancelled = true
    }
  }, [activePath, pendingRevealLine])

  return (
    <div className="flex h-full flex-col">
      {editorTabs.length > 0 && (
        <div className="flex h-8 flex-none items-center gap-px overflow-x-auto border-b border-slate-200 px-1 dark:border-slate-800">
          {editorTabs.map((path) => {
            const name = path.split('/').pop() ?? path
            return (
              <div
                key={path}
                onClick={() => openFile(path)}
                className={`group flex h-full cursor-pointer items-center gap-1.5 px-2.5 text-xs ${
                  path === activePath
                    ? 'border-b-2 border-sky-500 text-slate-800 dark:text-slate-100'
                    : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
                title={path}
              >
                <span>{name}</span>
                {dirtyFiles[path] && <span className="h-1.5 w-1.5 rounded-full bg-sky-500" />}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    closeEditorTab(path)
                  }}
                  className="rounded p-0.5 text-slate-400 opacity-0 hover:bg-slate-200 group-hover:opacity-100 dark:hover:bg-slate-700"
                  aria-label={`Close ${name}`}
                >
                  <CloseIcon size={10} />
                </button>
              </div>
            )
          })}
          <div className="ml-auto flex items-center gap-1 pr-1">
            {formatError && (
              <span className="max-w-64 truncate text-[10px] text-red-500" title={formatError}>
                {formatError}
              </span>
            )}
            {activePath && canFormat(activePath) && (
              <button
                onClick={() => void runFormat()}
                className="rounded border border-slate-300 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800"
                title="Format with Prettier (⇧⌥F)"
              >
                Format
              </button>
            )}
            {activePath && (
              <button
                onClick={() => setDiffOpen(true)}
                className="rounded border border-slate-300 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800"
                title="Compare the buffer with the saved file"
              >
                Diff
              </button>
            )}
          </div>
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        <div ref={containerRef} className="absolute inset-0" />
        {!activePath && (
          <div className="absolute inset-0 flex items-center justify-center bg-white text-sm text-slate-500 dark:bg-[#0e1420]">
            Select a file in Files to start editing.
          </div>
        )}
        {diffOpen && activePath && (
          <DiffOverlay path={activePath} onClose={() => setDiffOpen(false)} />
        )}
      </div>
    </div>
  )
}

/** Side-by-side diff: saved file on disk (left) vs the live buffer (right). */
function DiffOverlay({ path, onClose }: { path: string; onClose: () => void }): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const diff = monaco.editor.createDiffEditor(container, {
      automaticLayout: true,
      readOnly: false,
      originalEditable: false,
      renderSideBySide: true,
      fontSize: 12,
      theme: useShellStore.getState().theme === 'dark' ? 'vs-dark' : 'vs'
    })
    let original: monaco.editor.ITextModel | null = null
    void Promise.all([window.agweb.fs.read(path), ensureModel(path)]).then(
      ([diskResult, bufferModel]) => {
        if (!bufferModel) return
        original = monaco.editor.createModel(diskResult.content ?? '', bufferModel.getLanguageId())
        diff.setModel({ original, modified: bufferModel })
      }
    )
    return () => {
      diff.dispose()
      original?.dispose()
    }
  }, [path])

  return (
    <div className="absolute inset-0 z-10 flex flex-col bg-white dark:bg-[#0e1420]">
      <div className="flex h-8 flex-none items-center gap-2 border-b border-slate-200 px-3 text-xs dark:border-slate-800">
        <span className="font-semibold">Diff</span>
        <span className="text-slate-500">saved on disk ⟷ current buffer · {path}</span>
        <button
          onClick={onClose}
          className="ml-auto rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          aria-label="Close diff"
        >
          <CloseIcon />
        </button>
      </div>
      <div ref={containerRef} className="min-h-0 flex-1" />
    </div>
  )
}
