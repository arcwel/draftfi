import { dialog } from 'electron'
import { statSync } from 'node:fs'
import { basename } from 'node:path'
import type { RecentProject, WorkspaceInfo } from '@shared/ipc'
import { JsonStore } from './json-store'

const MAX_RECENT = 20

interface WorkspaceState {
  recent: RecentProject[]
}

const store = new JsonStore<WorkspaceState>('workspaces', { recent: [] })

let current: WorkspaceInfo | null = null

export function getCurrentWorkspace(): WorkspaceInfo | null {
  return current
}

export function getRecentProjects(): RecentProject[] {
  // Drop entries whose directory no longer exists.
  return store.read().recent.filter((p) => {
    try {
      return statSync(p.path).isDirectory()
    } catch {
      return false
    }
  })
}

export function openWorkspacePath(path: string): WorkspaceInfo | null {
  try {
    if (!statSync(path).isDirectory()) return null
  } catch {
    return null
  }
  current = { path, name: basename(path) }
  const recent = getRecentProjects().filter((p) => p.path !== path)
  recent.unshift({ ...current, lastOpenedAt: new Date().toISOString() })
  store.write({ recent: recent.slice(0, MAX_RECENT) })
  return current
}

export async function openWorkspaceDialog(): Promise<WorkspaceInfo | null> {
  const result = await dialog.showOpenDialog({
    title: 'Open Project Folder',
    properties: ['openDirectory', 'createDirectory']
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return openWorkspacePath(result.filePaths[0])
}
