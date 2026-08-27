import { promises as fsp, watch } from 'node:fs'
import type { FSWatcher } from 'node:fs'
import { resolve, sep } from 'node:path'
import { IpcEvents } from '@shared/ipc'
import type { FsEntry } from '@shared/ipc'
import { broadcast } from './windows'
import { getCurrentWorkspace } from './workspace'

/**
 * Workspace-scoped filesystem access for the Files and Editor blocks.
 * Every path is relative to the open workspace and validated to stay inside
 * it. A recursive watcher broadcasts change events (debounced) to windows.
 */

const MAX_FILE_BYTES = 2 * 1024 * 1024
const IGNORED = new Set(['node_modules', '.git', 'out', 'dist', '__pycache__'])

/** Resolve a workspace-relative path, refusing escapes. Null if no workspace. */
function resolveInWorkspace(rel: string): string | null {
  const root = getCurrentWorkspace()?.path
  if (!root) return null
  const full = resolve(root, rel)
  if (full !== root && !full.startsWith(root + sep)) return null
  return full
}

// Every op honors its {error} result contract: a thrown ENOENT/EEXIST/EACCES
// must reach the renderer as data, never as a rejected IPC invoke.
const message = (error: unknown): string => (error instanceof Error ? error.message : String(error))

export async function listDir(rel: string): Promise<FsEntry[]> {
  const full = resolveInWorkspace(rel)
  if (!full) return []
  try {
    const entries = await fsp.readdir(full, { withFileTypes: true })
    return entries
      .filter((e) => e.isDirectory() || e.isFile())
      .map((e): FsEntry => ({ name: e.name, kind: e.isDirectory() ? 'dir' : 'file' }))
      .sort((a, b) =>
        a.kind !== b.kind ? (a.kind === 'dir' ? -1 : 1) : a.name.localeCompare(b.name)
      )
  } catch {
    return []
  }
}

export async function readFile(rel: string): Promise<{ content?: string; error?: string }> {
  const full = resolveInWorkspace(rel)
  if (!full) return { error: 'no workspace' }
  try {
    const stat = await fsp.stat(full)
    if (stat.size > MAX_FILE_BYTES) return { error: 'File is too large to open (2 MB limit).' }
    return { content: await fsp.readFile(full, 'utf8') }
  } catch (error) {
    return { error: message(error) }
  }
}

export async function writeFile(rel: string, content: string): Promise<{ error?: string }> {
  const full = resolveInWorkspace(rel)
  if (!full) return { error: 'no workspace' }
  try {
    await fsp.writeFile(full, content, 'utf8')
    return {}
  } catch (error) {
    return { error: message(error) }
  }
}

export async function createEntry(rel: string, kind: 'file' | 'dir'): Promise<{ error?: string }> {
  const full = resolveInWorkspace(rel)
  if (!full) return { error: 'no workspace' }
  try {
    if (kind === 'dir') await fsp.mkdir(full, { recursive: true })
    else await fsp.writeFile(full, '', { flag: 'wx' })
    return {}
  } catch (error) {
    return { error: message(error) }
  }
}

export async function renameEntry(fromRel: string, toRel: string): Promise<{ error?: string }> {
  const from = resolveInWorkspace(fromRel)
  const to = resolveInWorkspace(toRel)
  if (!from || !to) return { error: 'no workspace' }
  try {
    await fsp.rename(from, to)
    return {}
  } catch (error) {
    return { error: message(error) }
  }
}

export async function deleteEntry(rel: string): Promise<{ error?: string }> {
  const full = resolveInWorkspace(rel)
  if (!full || full === getCurrentWorkspace()?.path) return { error: 'invalid path' }
  try {
    await fsp.rm(full, { recursive: true })
    return {}
  } catch (error) {
    return { error: message(error) }
  }
}

/* ---- Change watching ---- */

let watcher: FSWatcher | null = null
let notifyTimer: ReturnType<typeof setTimeout> | null = null

export function watchWorkspace(root: string | null): void {
  watcher?.close()
  watcher = null
  if (!root) return
  try {
    watcher = watch(root, { recursive: true }, (_event, filename) => {
      const top = String(filename ?? '').split(sep)[0]
      if (IGNORED.has(top)) return
      if (notifyTimer) clearTimeout(notifyTimer)
      notifyTimer = setTimeout(() => broadcast(IpcEvents.fsChanged, null, null), 150)
    })
  } catch (error) {
    console.warn('workspace watcher unavailable:', error)
  }
}
