import { useCallback, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import { load as parseYaml } from 'js-yaml'
import { parse as parseToml } from 'smol-toml'
import { useShellStore } from '@/store'
import { ensureModel, monaco } from '@/monaco'
import { JsonTree } from '@/components/JsonTree'
import { CsvTable } from '@/components/CsvTable'

/**
 * Document Studio: JSON, Markdown, YAML, TOML, and CSV rendered as styled,
 * human-readable documents in a browser tab, with a one-click toggle to an
 * editable Monaco source view. Re-renders live when the file changes on disk.
 */

export function DocStudio({ path }: { path: string }): React.JSX.Element {
  const [mode, setMode] = useState<'styled' | 'source'>('styled')
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const openFile = useShellStore((s) => s.openFile)
  const dirty = useShellStore((s) => s.dirtyFiles[path])

  const loadFile = useCallback((): void => {
    void window.agweb.fs.read(path).then((result) => {
      if (result.content !== undefined) {
        setContent(result.content)
        setError(null)
      } else {
        setError(result.error ?? 'Could not read file.')
      }
    })
  }, [path])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads after async IPC
    loadFile()
    return window.agweb.fs.onChanged(loadFile)
  }, [loadFile])

  const ext = path.split('.').pop()?.toLowerCase() ?? ''
  const name = path.split('/').pop() ?? path
  const segment = (id: 'styled' | 'source', label: string): React.JSX.Element => (
    <button
      onClick={() => setMode(id)}
      className={`rounded-md px-3 py-1 text-xs font-semibold ${
        mode === id
          ? 'bg-sky-600 text-white'
          : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
      }`}
    >
      {label}
    </button>
  )

  return (
    <div className="flex h-full flex-col bg-white text-slate-900 dark:bg-[#0b0f14] dark:text-slate-100">
      <div className="flex flex-none items-center gap-3 border-b border-slate-200 px-4 py-2 dark:border-slate-800">
        <span className="text-sm font-semibold">{name}</span>
        <span className="rounded bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-600 dark:text-sky-400">
          {ext}
        </span>
        {dirty && <span className="text-[11px] text-amber-500">unsaved edits in source</span>}
        <div className="ml-auto flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 dark:border-slate-700">
          {segment('styled', 'Styled')}
          {segment('source', 'Source')}
        </div>
        <button
          onClick={() => openFile(path)}
          className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800"
          title="Open in the Deck's editor block"
        >
          Open in Editor
        </button>
      </div>

      <div className="min-h-0 flex-1">
        {error && <div className="p-6 text-sm text-red-500">{error}</div>}
        {!error && content === null && <div className="p-6 text-sm text-slate-500">Loading…</div>}
        {!error && content !== null && mode === 'source' && <SourcePane path={path} />}
        {!error && content !== null && mode === 'styled' && (
          <StyledView ext={ext} content={content} />
        )}
      </div>
    </div>
  )
}

function StyledView({ ext, content }: { ext: string; content: string }): React.JSX.Element {
  if (ext === 'md' || ext === 'markdown') {
    return (
      <div className="h-full overflow-auto">
        <div className="doc-md mx-auto max-w-3xl px-8 py-8">
          <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
            {content}
          </Markdown>
        </div>
      </div>
    )
  }
  if (ext === 'csv' || ext === 'tsv') {
    return <CsvTable content={content} delimiter={ext === 'tsv' ? '\t' : undefined} />
  }
  // JSON / YAML / TOML share the tree inspector.
  try {
    const data =
      ext === 'json'
        ? (JSON.parse(content) as unknown)
        : ext === 'toml'
          ? parseToml(content)
          : parseYaml(content)
    return <JsonTree data={data} />
  } catch (parseError) {
    return (
      <div className="p-6 text-sm">
        <div className="font-semibold text-red-500">This file doesn&apos;t parse as {ext}.</div>
        <div className="mt-2 font-mono text-xs text-slate-500">{String(parseError)}</div>
      </div>
    )
  }
}

/** Editable Monaco bound to one file; ⌘S saves like the editor block. */
function SourcePane({ path }: { path: string }): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const theme = useShellStore((s) => s.theme)

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
      const model = editor.getModel()
      if (!model) return
      void window.agweb.fs.write(path, model.getValue()).then((result) => {
        if (!result.error) useShellStore.getState().setFileDirty(path, false)
      })
    })
    void ensureModel(path).then((model) => {
      if (model) editor.setModel(model)
    })
    return () => editor.dispose()
  }, [path])

  useEffect(() => {
    monaco.editor.setTheme(theme === 'dark' ? 'vs-dark' : 'vs')
  }, [theme])

  return <div ref={containerRef} className="h-full" />
}
