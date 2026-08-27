import { app } from 'electron'
import { spawn } from 'node:child_process'
import type { ChildProcess } from 'node:child_process'
import { createRequire } from 'node:module'
import { createInterface } from 'node:readline'
import { join } from 'node:path'
import { IpcEvents } from '@shared/ipc'
import { broadcast } from './windows'
import { getCurrentWorkspace } from './workspace'

/**
 * Terminal sessions live in the main process so they survive deck hide/reveal,
 * window moves, and detach. Preferred backend: node-pty in-process (packaged
 * builds run electron-rebuild). Fallback: a pty host child process under the
 * system Node, for dev setups where node-pty isn't built for Electron's ABI.
 */

const BUFFER_LIMIT = 200_000

type PtyLike = {
  write(data: string): void
  resize(cols: number, rows: number): void
  kill(): void
}

interface Session {
  backend: 'native' | 'child'
  proc?: PtyLike
  buffer: string
  running: boolean
}

const sessions = new Map<string, Session>()
const nodeRequire = createRequire(__filename)

type NodePtyModule = typeof import('node-pty')

let nativePty: NodePtyModule | null | undefined
function getNativePty(): NodePtyModule | null {
  if (nativePty !== undefined) return nativePty
  try {
    nativePty = nodeRequire('node-pty') as NodePtyModule
  } catch {
    nativePty = null
    console.warn('node-pty not loadable in Electron; using system-node pty host')
  }
  return nativePty
}

/* ---- Child pty-host fallback ---- */

let host: ChildProcess | null = null
function getHost(): ChildProcess | null {
  if (host && host.exitCode === null) return host
  try {
    const hostScript = join(app.getAppPath(), 'resources', 'pty-host.cjs')
    const ptyModule = nodeRequire.resolve('node-pty')
    host = spawn(process.env.AGWEB_NODE ?? 'node', [hostScript, ptyModule], {
      stdio: ['pipe', 'pipe', 'inherit']
    })
    host.on('exit', () => {
      for (const [id, session] of sessions) {
        if (session.backend === 'child' && session.running) endSession(id, -1)
      }
      host = null
    })
    createInterface({ input: host.stdout! }).on('line', (line) => {
      let msg: { ev: string; id: string; data?: string; code?: number }
      try {
        msg = JSON.parse(line)
      } catch {
        return
      }
      if (msg.ev === 'data' && typeof msg.data === 'string') pushData(msg.id, msg.data)
      else if (msg.ev === 'exit') endSession(msg.id, msg.code ?? 0)
    })
    return host
  } catch {
    host = null
    return null
  }
}

const hostSend = (msg: object): void => {
  getHost()?.stdin?.write(JSON.stringify(msg) + '\n')
}

/* ---- Session plumbing ---- */

function pushData(id: string, data: string): void {
  const session = sessions.get(id)
  if (!session) return
  session.buffer = (session.buffer + data).slice(-BUFFER_LIMIT)
  broadcast(IpcEvents.termData, { id, data }, null)
}

function endSession(id: string, code: number): void {
  const session = sessions.get(id)
  if (!session) return
  session.running = false
  session.proc = undefined
  broadcast(IpcEvents.termExit, { id, code }, null)
}

export function createTerminal(id: string, cols: number, rows: number): void {
  if (sessions.get(id)?.running) return
  const cwd = getCurrentWorkspace()?.path ?? app.getPath('home')
  const shell = process.env.SHELL || 'bash'

  const native = getNativePty()
  if (native) {
    const proc = native.spawn(shell, [], {
      name: 'xterm-256color',
      cols,
      rows,
      cwd,
      env: process.env as Record<string, string>
    })
    sessions.set(id, { backend: 'native', proc, buffer: '', running: true })
    proc.onData((data) => pushData(id, data))
    proc.onExit(({ exitCode }) => endSession(id, exitCode))
    return
  }

  sessions.set(id, { backend: 'child', buffer: '', running: true })
  hostSend({ op: 'create', id, cols, rows, cwd, shell })
}

export function writeTerminal(id: string, data: string): void {
  const session = sessions.get(id)
  if (!session?.running) return
  if (session.backend === 'native') session.proc?.write(data)
  else hostSend({ op: 'input', id, data })
}

export function resizeTerminal(id: string, cols: number, rows: number): void {
  const session = sessions.get(id)
  if (!session?.running) return
  try {
    if (session.backend === 'native') session.proc?.resize(cols, rows)
    else hostSend({ op: 'resize', id, cols, rows })
  } catch {
    // resizing a dying pty throws; ignore
  }
}

export function disposeTerminal(id: string): void {
  const session = sessions.get(id)
  if (!session) return
  if (session.backend === 'native') session.proc?.kill()
  else hostSend({ op: 'dispose', id })
  sessions.delete(id)
}

/** Reattach a renderer to a session: returns scrollback and liveness. */
export function attachTerminal(id: string): { buffer: string; running: boolean } {
  const session = sessions.get(id)
  return { buffer: session?.buffer ?? '', running: session?.running ?? false }
}

export function disposeAllTerminals(): void {
  for (const id of [...sessions.keys()]) disposeTerminal(id)
  host?.kill()
}
