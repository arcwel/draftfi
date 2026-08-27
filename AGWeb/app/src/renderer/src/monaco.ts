import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import JsonWorker from 'monaco-editor/language/json/json.worker.js?worker'
import CssWorker from 'monaco-editor/language/css/css.worker.js?worker'
import HtmlWorker from 'monaco-editor/language/html/html.worker.js?worker'
import TsWorker from 'monaco-editor/language/typescript/ts.worker.js?worker'

/** Monaco with locally bundled workers (no CDN — the app must work offline). */

self.MonacoEnvironment = {
  getWorker(_workerId: string, label: string): Worker {
    switch (label) {
      case 'json':
        return new JsonWorker()
      case 'css':
      case 'scss':
      case 'less':
        return new CssWorker()
      case 'html':
      case 'handlebars':
      case 'razor':
        return new HtmlWorker()
      case 'typescript':
      case 'javascript':
        return new TsWorker()
      default:
        return new EditorWorker()
    }
  }
}

const EXT_LANGUAGES: Record<string, string> = {
  ts: 'typescript',
  tsx: 'typescript',
  mts: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  json: 'json',
  css: 'css',
  scss: 'scss',
  html: 'html',
  htm: 'html',
  py: 'python',
  md: 'markdown',
  yml: 'yaml',
  yaml: 'yaml',
  toml: 'ini',
  sh: 'shell',
  svg: 'xml',
  xml: 'xml'
}

export function languageForPath(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() ?? ''
  return EXT_LANGUAGES[ext] ?? 'plaintext'
}

export { monaco }

/** Get or create the shared document model for a workspace file. */
export async function ensureModel(path: string): Promise<monaco.editor.ITextModel | null> {
  const uri = monaco.Uri.from({ scheme: 'agweb', path: `/${path}` })
  const existing = monaco.editor.getModel(uri)
  if (existing) return existing
  const result = await window.agweb.fs.read(path)
  if (result.content === undefined) return null
  const model = monaco.editor.createModel(result.content, languageForPath(path), uri)
  model.onDidChangeContent(() => {
    void import('@/store').then(({ useShellStore }) =>
      useShellStore.getState().setFileDirty(path, true)
    )
  })
  return model
}
