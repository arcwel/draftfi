import { useEffect, useRef } from 'react'
import { languageForPath, monaco } from '@/monaco'
import { useShellStore } from '@/store'
import { CloseIcon } from '@/components/icons'

/**
 * Monaco-backed editor. Documents are Monaco models keyed by workspace path
 * (shared by every editor instance in this window); the open-tab list and
 * focused document live in the store, synced across windows.
 */

async function ensureModel(path: string): Promise<monaco.editor.ITextModel | null> {
  const uri = monaco.Uri.from({ scheme: 'agweb', path: `/${path}` })
  const existing = monaco.editor.getModel(uri)
  if (existing) return existing
  const result = await window.agweb.fs.read(path)
  if (result.content === undefined) return null
  const model = monaco.editor.createModel(result.content, languageForPath(path), uri)
  model.onDidChangeContent(() => {
    useShellStore.getState().setFileDirty(path, true)
  })
  return model
}

export function EditorBlock(): React.JSX.Element {
  const editorTabs = useShellStore((s) => s.editorTabs)
  const activePath = useShellStore((s) => s.activeEditorPath)
  const dirtyFiles = useShellStore((s) => s.dirtyFiles)
  const theme = useShellStore((s) => s.theme)
  const { openFile, closeEditorTab } = useShellStore()

  const containerRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const activePathRef = useRef(activePath)
  useEffect(() => {
    activePathRef.current = activePath
  }, [activePath])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const editor = monaco.editor.create(container, {
      automaticLayout: true,
      fontSize: 13,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      theme: theme === 'dark' ? 'vs-dark' : 'vs'
    })
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      const path = activePathRef.current
      const model = editor.getModel()
      if (!path || !model) return
      void window.agweb.fs.write(path, model.getValue()).then((result) => {
        if (!result.error) useShellStore.getState().setFileDirty(path, false)
      })
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
      if (!cancelled && model && editorRef.current) editorRef.current.setModel(model)
    })
    return () => {
      cancelled = true
    }
  }, [activePath])

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
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        <div ref={containerRef} className="absolute inset-0" />
        {!activePath && (
          <div className="absolute inset-0 flex items-center justify-center bg-white text-sm text-slate-500 dark:bg-[#0e1420]">
            Select a file in Files to start editing.
          </div>
        )}
      </div>
    </div>
  )
}
