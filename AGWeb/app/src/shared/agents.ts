/** Agent orchestration domain types, shared by main and every renderer. */

export type AgentStatus =
  'planning' | 'awaiting_approval' | 'running' | 'done' | 'rejected' | 'error' | 'stopped'

export type PlanStepKind = 'edit' | 'command' | 'inspect' | 'verify' | 'other'

export interface PlanStep {
  kind: PlanStepKind
  title: string
  detail?: string
}

export type AgentLogKind =
  'status' | 'text' | 'tool' | 'edit' | 'command' | 'browser' | 'screenshot' | 'error'

export interface AgentLogEntry {
  ts: number
  kind: AgentLogKind
  text: string
  /** For 'edit' entries: the touched file and its before/after content.
   *  For 'screenshot' entries: the workspace-relative PNG path. */
  path?: string
  before?: string
  after?: string
}

export interface AgentSessionInfo {
  id: string
  task: string
  status: AgentStatus
  workspacePath: string | null
  plan: PlanStep[]
  log: AgentLogEntry[]
  createdAt: number
}

export interface AgentKeyStatus {
  /** An API key is available (settings or ANTHROPIC_API_KEY). */
  configured: boolean
  /** Mock provider active (AGWEB_AGENT_MOCK=1) — no key or network needed. */
  mock: boolean
  model: string
}
