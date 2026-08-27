import Anthropic from '@anthropic-ai/sdk'
import { exec } from 'node:child_process'
import { app } from 'electron'
import { IpcEvents } from '@shared/ipc'
import type { AgentKeyStatus, AgentLogEntry, AgentSessionInfo, PlanStep } from '@shared/agents'
import { broadcast } from './windows'
import { getCurrentWorkspace } from './workspace'
import { createEntry, listDir, readFile, writeFile } from './fs'
import { searchWorkspace } from './search'
import { JsonStore } from './json-store'

/**
 * Agent orchestration (PRD flow 4.1): a task is planned first, the plan is
 * held for user approval, and only then does the agent execute — a manual
 * tool-use loop over workspace-scoped tools, with every action logged to
 * Mission Control. Sessions persist across restarts; several can run at once.
 *
 * Provider: Claude (claude-opus-5, adaptive thinking, server-side refusal
 * fallbacks). AGWEB_AGENT_MOCK=1 swaps in a deterministic scripted provider
 * so the pipeline is testable without keys or network.
 */

const MODEL = process.env.AGWEB_AGENT_MODEL || 'claude-opus-5'
const MAX_ITERATIONS = 40
const COMMAND_TIMEOUT_MS = 120_000
const OUTPUT_CAP = 20_000
const LOG_CAP = 500

interface AgentSession extends AgentSessionInfo {
  stopRequested: boolean
}

const sessions = new Map<string, AgentSession>()
let nextSessionId = 1

const settingsStore = new JsonStore<{ apiKey?: string }>('agent-settings', {})
const sessionStore = new JsonStore<{ sessions: AgentSessionInfo[] }>('agent-sessions', {
  sessions: []
})

/* ---- Session bookkeeping ---- */

function toInfo(session: AgentSession): AgentSessionInfo {
  return {
    id: session.id,
    task: session.task,
    status: session.status,
    workspacePath: session.workspacePath,
    plan: session.plan,
    log: session.log,
    createdAt: session.createdAt
  }
}

function persistSessions(): void {
  sessionStore.write({ sessions: [...sessions.values()].map(toInfo) })
}

function update(session: AgentSession, patch: Partial<AgentSessionInfo>): void {
  Object.assign(session, patch)
  broadcast(IpcEvents.agentUpdate, toInfo(session), null)
  persistSessions()
}

function log(session: AgentSession, entry: Omit<AgentLogEntry, 'ts'>): void {
  session.log = [...session.log.slice(-LOG_CAP), { ts: Date.now(), ...entry }]
  broadcast(IpcEvents.agentUpdate, toInfo(session), null)
  persistSessions()
}

export function initAgents(): void {
  // Sessions from a previous app run can't still be executing.
  for (const info of sessionStore.read().sessions) {
    const session: AgentSession = { ...info, stopRequested: false }
    if (session.status === 'planning' || session.status === 'running') {
      session.status = 'error'
      session.log = [
        ...session.log,
        { ts: Date.now(), kind: 'error', text: 'Interrupted by app restart.' }
      ]
    }
    sessions.set(session.id, session)
    nextSessionId = Math.max(nextSessionId, Number(session.id.replace('agent-', '')) + 1 || 1)
  }
}

export function listAgentSessions(): AgentSessionInfo[] {
  return [...sessions.values()].map(toInfo).sort((a, b) => b.createdAt - a.createdAt)
}

export function getAgentKeyStatus(): AgentKeyStatus {
  return {
    configured: Boolean(settingsStore.read().apiKey || process.env.ANTHROPIC_API_KEY),
    mock: process.env.AGWEB_AGENT_MOCK === '1',
    model: MODEL
  }
}

export function setAgentApiKey(key: string): void {
  settingsStore.write({ apiKey: key.trim() || undefined })
}

/* ---- Lifecycle ---- */

export function startAgentTask(task: string): string {
  const session: AgentSession = {
    id: `agent-${nextSessionId++}`,
    task,
    status: 'planning',
    workspacePath: getCurrentWorkspace()?.path ?? null,
    plan: [],
    log: [],
    createdAt: Date.now(),
    stopRequested: false
  }
  sessions.set(session.id, session)
  log(session, { kind: 'status', text: 'Planning…' })

  void planTask(session).catch((error) => {
    log(session, { kind: 'error', text: String(error) })
    update(session, { status: 'error' })
  })
  return session.id
}

export function approveAgentPlan(id: string): void {
  const session = sessions.get(id)
  if (!session || session.status !== 'awaiting_approval') return
  update(session, { status: 'running' })
  log(session, { kind: 'status', text: 'Plan approved — executing.' })
  void executeTask(session).catch((error) => {
    log(session, { kind: 'error', text: String(error) })
    update(session, { status: 'error' })
  })
}

export function rejectAgentPlan(id: string): void {
  const session = sessions.get(id)
  if (!session || session.status !== 'awaiting_approval') return
  log(session, { kind: 'status', text: 'Plan rejected.' })
  update(session, { status: 'rejected' })
}

export function stopAgent(id: string): void {
  const session = sessions.get(id)
  if (!session) return
  session.stopRequested = true
  log(session, { kind: 'status', text: 'Stop requested.' })
}

/* ---- Planning ---- */

const PLAN_TOOL: Anthropic.Tool = {
  name: 'create_plan',
  description: 'Submit the step-by-step execution plan for the task.',
  input_schema: {
    type: 'object',
    additionalProperties: false,
    required: ['steps'],
    properties: {
      steps: {
        type: 'array',
        items: {
          type: 'object',
          additionalProperties: false,
          required: ['kind', 'title'],
          properties: {
            kind: { type: 'string', enum: ['edit', 'command', 'inspect', 'verify', 'other'] },
            title: { type: 'string' },
            detail: { type: 'string' }
          }
        }
      }
    }
  },
  strict: true
}

function getClient(): Anthropic {
  const apiKey = settingsStore.read().apiKey || process.env.ANTHROPIC_API_KEY
  if (!apiKey) throw new Error('No API key configured. Add one in the Agents block.')
  return new Anthropic({ apiKey })
}

async function planTask(session: AgentSession): Promise<void> {
  if (process.env.AGWEB_AGENT_MOCK === '1') {
    session.plan = mockPlan(session.task)
    log(session, { kind: 'status', text: 'Plan ready (mock provider).' })
    update(session, { status: 'awaiting_approval' })
    return
  }

  const client = getClient()
  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 16000,
    system:
      'You are the planning stage of AGWeb, an agent-first IDE. Produce a concise, ' +
      'concrete execution plan for the task in the given workspace. Steps should be ' +
      'few and meaningful (typically 2-6). Use the create_plan tool.',
    tool_choice: { type: 'tool', name: 'create_plan' },
    tools: [PLAN_TOOL],
    messages: [
      {
        role: 'user',
        content: `Workspace: ${session.workspacePath ?? '(none open)'}\n\nTask: ${session.task}`
      }
    ]
  })
  const toolUse = response.content.find((b): b is Anthropic.ToolUseBlock => b.type === 'tool_use')
  const input = toolUse?.input as { steps?: PlanStep[] } | undefined
  session.plan = input?.steps ?? []
  if (session.plan.length === 0) throw new Error('The model returned an empty plan.')
  log(session, { kind: 'status', text: `Plan ready (${session.plan.length} steps).` })
  update(session, { status: 'awaiting_approval' })
}

/* ---- Execution tools ---- */

const EXEC_TOOLS: Anthropic.Tool[] = [
  {
    name: 'read_file',
    description: 'Read a UTF-8 text file. Path is relative to the workspace root.',
    input_schema: {
      type: 'object',
      additionalProperties: false,
      required: ['path'],
      properties: { path: { type: 'string' } }
    },
    strict: true
  },
  {
    name: 'write_file',
    description:
      'Create or overwrite a text file with the given content. Path is relative to the workspace root; parent directories are created as needed.',
    input_schema: {
      type: 'object',
      additionalProperties: false,
      required: ['path', 'content'],
      properties: { path: { type: 'string' }, content: { type: 'string' } }
    },
    strict: true
  },
  {
    name: 'list_dir',
    description: 'List a directory in the workspace ("" for the root).',
    input_schema: {
      type: 'object',
      additionalProperties: false,
      required: ['path'],
      properties: { path: { type: 'string' } }
    },
    strict: true
  },
  {
    name: 'search',
    description: 'Search file contents across the workspace. Returns path, line, text.',
    input_schema: {
      type: 'object',
      additionalProperties: false,
      required: ['query'],
      properties: { query: { type: 'string' } }
    },
    strict: true
  },
  {
    name: 'run_command',
    description:
      'Run a shell command in the workspace root. Returns stdout+stderr (capped) and the exit code. 120s timeout.',
    input_schema: {
      type: 'object',
      additionalProperties: false,
      required: ['command'],
      properties: { command: { type: 'string' } }
    },
    strict: true
  }
]

function runCommand(command: string, cwd: string): Promise<string> {
  return new Promise((resolve) => {
    exec(
      command,
      { cwd, timeout: COMMAND_TIMEOUT_MS, maxBuffer: 4 * 1024 * 1024 },
      (error, stdout, stderr) => {
        const code = error ? ((error as { code?: number }).code ?? 1) : 0
        const output = `${stdout}${stderr}`.slice(0, OUTPUT_CAP)
        resolve(`exit code: ${code}\n${output}`)
      }
    )
  })
}

async function executeTool(
  session: AgentSession,
  name: string,
  input: Record<string, unknown>
): Promise<string> {
  const cwd = session.workspacePath ?? app.getPath('home')
  switch (name) {
    case 'read_file': {
      const result = await readFile(String(input.path ?? ''))
      return result.error ? `error: ${result.error}` : (result.content ?? '')
    }
    case 'write_file': {
      const path = String(input.path ?? '')
      const before = (await readFile(path)).content ?? ''
      const dir = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : ''
      if (dir) await createEntry(dir, 'dir')
      const result = await writeFile(path, String(input.content ?? ''))
      if (result.error) return `error: ${result.error}`
      log(session, {
        kind: 'edit',
        text: `Edited ${path}`,
        path,
        before,
        after: String(input.content ?? '')
      })
      return 'ok'
    }
    case 'list_dir': {
      const entries = await listDir(String(input.path ?? ''))
      return entries.map((e) => `${e.kind === 'dir' ? 'dir ' : 'file'} ${e.name}`).join('\n')
    }
    case 'search': {
      const hits = await searchWorkspace(String(input.query ?? ''))
      return hits
        .slice(0, 50)
        .map((h) => `${h.path}:${h.line}: ${h.text}`)
        .join('\n')
    }
    case 'run_command': {
      const command = String(input.command ?? '')
      log(session, { kind: 'command', text: `$ ${command}` })
      const output = await runCommand(command, cwd)
      log(session, { kind: 'text', text: output.slice(0, 2000) })
      return output
    }
    default:
      return `error: unknown tool ${name}`
  }
}

/* ---- Execution loop ---- */

async function executeTask(session: AgentSession): Promise<void> {
  if (process.env.AGWEB_AGENT_MOCK === '1') {
    await mockExecute(session)
    return
  }

  const client = getClient()
  const messages: Anthropic.Beta.BetaMessageParam[] = [
    {
      role: 'user',
      content:
        `Task: ${session.task}\n\nApproved plan:\n` +
        session.plan.map((s, i) => `${i + 1}. [${s.kind}] ${s.title}`).join('\n')
    }
  ]

  for (let iteration = 0; iteration < MAX_ITERATIONS; iteration++) {
    if (session.stopRequested) {
      update(session, { status: 'stopped' })
      return
    }

    const stream = client.beta.messages.stream({
      model: MODEL,
      max_tokens: 32000,
      // Route policy declines to a fallback model server-side (skill default).
      betas: ['server-side-fallback-2026-07-01'],
      fallbacks: 'default',
      system:
        "You are AGWeb's execution agent, working inside the workspace at " +
        `${session.workspacePath ?? '(no workspace)'} with workspace-scoped tools. ` +
        'Follow the approved plan, keep changes minimal, and end with a short summary ' +
        'of what you did and how you verified it.',
      tools: EXEC_TOOLS,
      messages
    } as Parameters<typeof client.beta.messages.stream>[0])
    const message = await stream.finalMessage()

    for (const block of message.content) {
      if (block.type === 'text' && block.text.trim()) {
        log(session, { kind: 'text', text: block.text.trim() })
      }
    }

    if (message.stop_reason === 'refusal') {
      log(session, { kind: 'error', text: 'The model declined this request (safety policy).' })
      update(session, { status: 'error' })
      return
    }
    if (message.stop_reason === 'pause_turn') {
      messages.push({ role: 'assistant', content: message.content })
      continue
    }
    if (message.stop_reason !== 'tool_use') {
      update(session, { status: 'done' })
      log(session, { kind: 'status', text: 'Task complete.' })
      return
    }

    const toolUses = message.content.filter(
      (b): b is Anthropic.Beta.BetaToolUseBlock => b.type === 'tool_use'
    )
    messages.push({ role: 'assistant', content: message.content })

    const results: Anthropic.Beta.BetaToolResultBlockParam[] = []
    for (const tool of toolUses) {
      log(session, {
        kind: 'tool',
        text: `→ ${tool.name}(${JSON.stringify(tool.input).slice(0, 200)})`
      })
      let content: string
      try {
        content = await executeTool(session, tool.name, tool.input as Record<string, unknown>)
      } catch (error) {
        content = `error: ${String(error)}`
      }
      results.push({ type: 'tool_result', tool_use_id: tool.id, content })
    }
    messages.push({ role: 'user', content: results })
  }

  log(session, { kind: 'error', text: `Stopped after ${MAX_ITERATIONS} iterations.` })
  update(session, { status: 'error' })
}

/* ---- Mock provider (AGWEB_AGENT_MOCK=1): deterministic, offline ---- */

function mockPlan(task: string): PlanStep[] {
  return [
    { kind: 'edit', title: 'Write AGENT_NOTE.md recording the task', detail: task },
    { kind: 'command', title: 'Verify by listing the workspace' },
    { kind: 'verify', title: 'Summarize the result' }
  ]
}

async function mockExecute(session: AgentSession): Promise<void> {
  await executeTool(session, 'write_file', {
    path: 'AGENT_NOTE.md',
    content: `# Agent note\n\nTask: ${session.task}\n\nCompleted by the mock agent.\n`
  })
  const output = await executeTool(session, 'run_command', { command: 'ls' })
  log(session, {
    kind: 'text',
    text: `Wrote AGENT_NOTE.md and verified the workspace listing (${output.split('\n').length - 1} lines). Task recorded.`
  })
  update(session, { status: 'done' })
  log(session, { kind: 'status', text: 'Task complete.' })
}
