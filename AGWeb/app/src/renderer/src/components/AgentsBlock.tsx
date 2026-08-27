import { useEffect, useMemo, useRef, useState } from 'react'
import type { AgentLogEntry, AgentSessionInfo, AgentStatus } from '@shared/agents'
import { monaco } from '@/monaco'
import { useShellStore } from '@/store'
import { CloseIcon } from '@/components/icons'

/**
 * Mission Control (Phase 6): compose a task, review + approve the agent's
 * plan, then watch execution live. Sessions come from the main process and
 * are mirrored into every window via agentUpdate events.
 */

const STATUS_STYLES: Record<AgentStatus, string> = {
  planning: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400',
  awaiting_approval: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-400',
  running: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400',
  done: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400',
  rejected: 'bg-slate-100 text-slate-500 dark:bg-slate-500/15 dark:text-slate-400',
  error: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
  stopped: 'bg-slate-100 text-slate-500 dark:bg-slate-500/15 dark:text-slate-400'
}

const STATUS_LABELS: Record<AgentStatus, string> = {
  planning: 'Planning',
  awaiting_approval: 'Awaiting approval',
  running: 'Running',
  done: 'Done',
  rejected: 'Rejected',
  error: 'Error',
  stopped: 'Stopped'
}

const PLAN_KIND_GLYPHS: Record<string, string> = {
  edit: '✎',
  command: '❯',
  inspect: '🔍',
  verify: '✓',
  other: '·'
}

export function AgentsBlock(): React.JSX.Element {
  const agentSessions = useShellStore((s) => s.agentSessions)
  const [task, setTask] = useState('')
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [diffEntry, setDiffEntry] = useState<AgentLogEntry | null>(null)

  const sessions = useMemo(
    () => Object.values(agentSessions).sort((a, b) => b.createdAt - a.createdAt),
    [agentSessions]
  )
  const anyFinished = sessions.some((s) => TERMINAL_STATUSES.has(s.status))

  const startTask = async (): Promise<void> => {
    const trimmed = task.trim()
    if (!trimmed || starting) return
    setStarting(true)
    setStartError(null)
    try {
      await window.agweb.agents.start(trimmed)
      setTask('')
    } catch (error) {
      setStartError(String(error))
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="relative flex h-full flex-col text-xs">
      <KeyBanner />
      <div className="flex flex-none items-start gap-2 border-b border-slate-200 p-2.5 dark:border-slate-800">
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void startTask()
          }}
          placeholder="Describe a task for the agent… (⌘↵ to plan)"
          rows={2}
          className="min-w-0 flex-1 resize-none rounded-md border border-slate-300 bg-transparent px-2.5 py-1.5 outline-none placeholder:text-slate-400 focus:border-sky-500 dark:border-slate-600"
          data-testid="agent-task-input"
        />
        <button
          onClick={() => void startTask()}
          disabled={!task.trim() || starting}
          className="rounded-md bg-sky-600 px-3 py-1.5 font-semibold text-white hover:bg-sky-500 disabled:opacity-40"
          data-testid="agent-plan-button"
        >
          {starting ? 'Planning…' : 'Plan task'}
        </button>
      </div>
      {startError && (
        <div className="flex-none px-3 py-1.5 text-[11px] text-red-500">{startError}</div>
      )}
      {anyFinished && (
        <div className="flex flex-none justify-end border-b border-slate-200 px-2.5 py-1 dark:border-slate-800">
          <button
            onClick={() => void window.agweb.agents.clearFinished()}
            className="text-[10px] font-semibold text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            title="Remove finished sessions and their stored artifacts"
            data-testid="agent-clear-finished"
          >
            Clear finished
          </button>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {sessions.length === 0 && (
          <div className="p-3 text-slate-500">
            No agent sessions yet. Describe a task above — the agent plans first and waits for your
            approval before touching the workspace.
          </div>
        )}
        {sessions.map((session) => (
          <SessionCard key={session.id} session={session} onShowDiff={setDiffEntry} />
        ))}
      </div>
      {diffEntry && <EditDiffModal entry={diffEntry} onClose={() => setDiffEntry(null)} />}
    </div>
  )
}

/** API-key entry, shown until a key is configured (hidden for the mock provider). */
function KeyBanner(): React.JSX.Element | null {
  const [status, setStatus] = useState<{ configured: boolean; mock: boolean; model: string }>()
  const [key, setKey] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    void window.agweb.agents.keyStatus().then(setStatus)
  }, [])

  if (!status || status.configured || status.mock) return null

  const save = async (): Promise<void> => {
    if (!key.trim() || saving) return
    setSaving(true)
    const next = await window.agweb.agents.setKey(key)
    setStatus(next)
    setKey('')
    setSaving(false)
  }

  return (
    <div className="flex flex-none items-center gap-2 border-b border-amber-300/50 bg-amber-50 px-2.5 py-2 dark:bg-amber-500/10">
      <span className="text-amber-700 dark:text-amber-400">
        Anthropic API key required ({status.model}):
      </span>
      <input
        type="password"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void save()
        }}
        placeholder="sk-ant-…"
        className="min-w-0 flex-1 rounded border border-amber-300 bg-white px-2 py-1 outline-none focus:border-amber-500 dark:border-amber-500/40 dark:bg-transparent"
      />
      <button
        onClick={() => void save()}
        disabled={!key.trim() || saving}
        className="rounded bg-amber-600 px-2.5 py-1 font-semibold text-white hover:bg-amber-500 disabled:opacity-40"
      >
        Save
      </button>
    </div>
  )
}

const TERMINAL_STATUSES: ReadonlySet<AgentStatus> = new Set([
  'done',
  'error',
  'stopped',
  'rejected'
])

function SessionCard({
  session,
  onShowDiff
}: {
  session: AgentSessionInfo
  onShowDiff: (entry: AgentLogEntry) => void
}): React.JSX.Element {
  const [expanded, setExpanded] = useState(true)
  const active = session.status === 'planning' || session.status === 'running'
  const finished = TERMINAL_STATUSES.has(session.status)

  return (
    <div
      className="border-b border-slate-200 dark:border-slate-800"
      data-testid={`agent-session-${session.id}`}
    >
      <div
        onClick={() => setExpanded((v) => !v)}
        className="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-900"
      >
        <span
          className={`flex-none rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_STYLES[session.status]}`}
          data-testid="agent-status"
        >
          {STATUS_LABELS[session.status]}
        </span>
        <span className="min-w-0 flex-1 truncate font-medium text-slate-700 dark:text-slate-200">
          {session.task}
        </span>
        {active && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              void window.agweb.agents.stop(session.id)
            }}
            className="flex-none rounded border border-slate-300 px-2 py-0.5 text-[10px] font-semibold text-slate-500 hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800"
          >
            Stop
          </button>
        )}
        {finished && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              void window.agweb.agents.openReport(session.id)
            }}
            className="flex-none rounded border border-sky-400/60 px-2 py-0.5 text-[10px] font-semibold text-sky-600 hover:bg-sky-50 dark:text-sky-400 dark:hover:bg-sky-500/10"
            title="Open the execution report (plan, timeline, diffs, screenshots) in a browser tab"
            data-testid="agent-report"
          >
            Report
          </button>
        )}
      </div>

      {expanded && (
        <div className="px-3 pb-2.5">
          {session.plan.length > 0 && (
            <div className="mb-2 rounded-md border border-slate-200 dark:border-slate-800">
              <div className="border-b border-slate-200 px-2.5 py-1.5 text-[10px] font-semibold tracking-wide text-slate-400 uppercase dark:border-slate-800">
                Plan
              </div>
              <ol className="px-2.5 py-1.5" data-testid="agent-plan">
                {session.plan.map((step, i) => (
                  <li key={i} className="flex gap-2 py-0.5 text-slate-600 dark:text-slate-300">
                    <span className="flex-none text-slate-400">
                      {PLAN_KIND_GLYPHS[step.kind] ?? '·'}
                    </span>
                    <span>
                      {step.title}
                      {step.detail && <span className="text-slate-400"> — {step.detail}</span>}
                    </span>
                  </li>
                ))}
              </ol>
              {session.status === 'awaiting_approval' && (
                <div className="flex gap-2 border-t border-slate-200 px-2.5 py-2 dark:border-slate-800">
                  <button
                    onClick={() => void window.agweb.agents.approve(session.id)}
                    className="rounded-md bg-emerald-600 px-3 py-1 font-semibold text-white hover:bg-emerald-500"
                    data-testid="agent-approve"
                  >
                    Approve &amp; run
                  </button>
                  <button
                    onClick={() => void window.agweb.agents.reject(session.id)}
                    className="rounded-md border border-slate-300 px-3 py-1 font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                    data-testid="agent-reject"
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>
          )}
          <ActivityFeed entries={session.log} onShowDiff={onShowDiff} />
        </div>
      )}
    </div>
  )
}

const LOG_COLORS: Record<AgentLogEntry['kind'], string> = {
  status: 'text-sky-600 dark:text-sky-400',
  text: 'text-slate-600 dark:text-slate-300',
  tool: 'text-slate-400',
  edit: 'text-emerald-600 dark:text-emerald-400',
  command: 'text-indigo-600 dark:text-indigo-400',
  browser: 'text-cyan-600 dark:text-cyan-400',
  screenshot: 'text-purple-600 dark:text-purple-400',
  error: 'text-red-500'
}

function ActivityFeed({
  entries,
  onShowDiff
}: {
  entries: AgentLogEntry[]
  onShowDiff: (entry: AgentLogEntry) => void
}): React.JSX.Element {
  return (
    <div className="space-y-0.5 font-mono text-[11px]" data-testid="agent-log">
      {entries.map((entry, i) => (
        <div key={i} className={`flex gap-2 ${LOG_COLORS[entry.kind]}`}>
          <span className="flex-none text-slate-400/60">
            {new Date(entry.ts).toLocaleTimeString()}
          </span>
          <span className="min-w-0 whitespace-pre-wrap break-words">
            {entry.text}
            {entry.kind === 'edit' && entry.path && (
              <button
                onClick={() => onShowDiff(entry)}
                className="ml-2 rounded border border-emerald-400/50 px-1.5 text-[10px] font-semibold hover:bg-emerald-500/10"
              >
                View diff
              </button>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Monaco diff of one agent edit: file before (left) vs after (right). */
function EditDiffModal({
  entry,
  onClose
}: {
  entry: AgentLogEntry
  onClose: () => void
}): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const diff = monaco.editor.createDiffEditor(container, {
      automaticLayout: true,
      readOnly: true,
      originalEditable: false,
      renderSideBySide: true,
      fontSize: 12,
      theme: useShellStore.getState().theme === 'dark' ? 'vs-dark' : 'vs'
    })
    const original = monaco.editor.createModel(entry.before ?? '')
    const modified = monaco.editor.createModel(entry.after ?? '')
    diff.setModel({ original, modified })
    return () => {
      diff.dispose()
      original.dispose()
      modified.dispose()
    }
  }, [entry])

  return (
    <div className="absolute inset-0 z-10 flex flex-col bg-white dark:bg-[#0e1420]">
      <div className="flex h-8 flex-none items-center gap-2 border-b border-slate-200 px-3 text-xs dark:border-slate-800">
        <span className="font-semibold">Agent edit</span>
        <span className="text-slate-500">before ⟷ after · {entry.path}</span>
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

/** Logs block: the merged live activity feed across every agent session. */
export function LogsBlock(): React.JSX.Element {
  const agentSessions = useShellStore((s) => s.agentSessions)
  const scrollRef = useRef<HTMLDivElement>(null)

  const entries = useMemo(() => {
    const all: (AgentLogEntry & { sessionId: string; task: string })[] = []
    for (const session of Object.values(agentSessions)) {
      for (const entry of session.log) {
        all.push({ ...entry, sessionId: session.id, task: session.task })
      }
    }
    return all.sort((a, b) => a.ts - b.ts)
  }, [agentSessions])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [entries.length])

  if (entries.length === 0) {
    return (
      <div className="h-full p-3 font-mono text-xs text-slate-500">
        No agent activity yet. Logs stream here while agents plan and execute.
      </div>
    )
  }

  return (
    <div
      ref={scrollRef}
      className="h-full overflow-y-auto p-2.5 font-mono text-[11px]"
      data-testid="logs-feed"
    >
      {entries.map((entry, i) => (
        <div key={i} className={`flex gap-2 py-px ${LOG_COLORS[entry.kind]}`}>
          <span className="flex-none text-slate-400/60">
            {new Date(entry.ts).toLocaleTimeString()}
          </span>
          <span className="flex-none text-slate-400" title={entry.task}>
            [{entry.sessionId}]
          </span>
          <span className="min-w-0 whitespace-pre-wrap break-words">{entry.text}</span>
        </div>
      ))}
    </div>
  )
}
