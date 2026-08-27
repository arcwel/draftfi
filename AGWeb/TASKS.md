# AGWeb — Agent-First Universal IDE & Browser — Build Task List

Derived from `AGWeb/PRD.md`. Phases are ordered by dependency; tasks within a phase can often run in parallel.

**Status:** Draft — awaiting review. No implementation started.

---

## Phase 0 — Project Setup & Scaffolding

- [ ] 0.1 Initialize project structure inside `AGWeb/` with `.gitignore` (Node, Electron build output, Python, `.env`)
- [ ] 0.2 Choose and document open-source license consistent with Electron/Chromium/Code - OSS dependencies (MIT recommended)
- [ ] 0.3 Scaffold Electron + TypeScript + React app (main process, preload, renderer) with Vite bundling
- [ ] 0.4 Add Tailwind CSS and base design tokens for the Mission Control shell
- [ ] 0.5 Integrate Monaco Editor as the embedded code editor component
- [ ] 0.6 Set up Python tooling workspace (`backend/` or `tools/`) with venv, ruff, pytest for agent/proxy backend services
- [ ] 0.7 Dev tooling: ESLint, Prettier, TypeScript strict mode, pre-commit hooks
- [ ] 0.8 CI pipeline: lint + typecheck + unit tests on push
- [ ] 0.9 Write `AGWeb/README.md` with vision, architecture diagram, and dev setup steps

## Phase 1 — Application Shell & Window Management

- [ ] 1.1 Electron main-process architecture: window lifecycle, single-instance lock, crash recovery
- [ ] 1.2 Multi-pane layout shell: sidebar (projects/agents), tabbed center stage (editor / browser / slides), bottom dock (terminal / logs)
- [ ] 1.3 Secure IPC contract between main, preload, and renderer (contextIsolation on, no nodeIntegration in renderer)
- [ ] 1.4 Cross-window communication layer using PostMessage/Postmate for embedded previews
- [ ] 1.5 Workspace/project model: open folder, recent projects, per-project state persistence
- [ ] 1.6 Theming (light/dark) and keyboard-shortcut framework

## Phase 2 — Integrated Browser (Chromium)

- [ ] 2.1 Embed Chromium browser tabs via Electron `WebContentsView` with standard navigation chrome (back/forward/reload/URL bar)
- [ ] 2.2 Tab management: open/close/reorder, session restore, per-tab process isolation
- [ ] 2.3 DevTools access per tab
- [ ] 2.4 Chrome extension loading support (Manifest V3 via Electron's extensions API; document limitations)
- [ ] 2.5 Local proxy layer that strips frame-busting headers (X-Frame-Options, CSP frame-ancestors) for development-preview embedding only
- [ ] 2.6 Proxy safety rails: enabled only for allowlisted dev origins, clear UI indicator when active
- [ ] 2.7 Download handling, permission prompts (camera/mic/geolocation), and popup policy

## Phase 3 — IDE Core (Editor, Files, Terminal)

- [ ] 3.1 File explorer with create/rename/delete/move and file-watcher refresh
- [ ] 3.2 Monaco integration: syntax highlighting + IntelliSense for JSON, HTML, CSS, JavaScript/TypeScript, Python
- [ ] 3.3 Formatter integration (Prettier for web languages, ruff/black for Python)
- [ ] 3.4 Integrated terminal (node-pty + xterm.js) with multiple sessions
- [ ] 3.5 Diff viewer for reviewing agent-proposed changes before/after apply
- [ ] 3.6 Search across project (ripgrep-backed)

## Phase 4 — Live Preview & Slide Runtime

- [ ] 4.1 Dev-server manager: detect/boot local dev servers per project, port allocation, health checks
- [ ] 4.2 Live preview pane with hot-reload wired to file changes
- [ ] 4.3 Style isolation for embedded previews (Shadow DOM / CSS Modules) so host UI and preview don't bleed
- [ ] 4.4 Reveal.js slide runtime: render decks from project files in a synchronized preview pane
- [ ] 4.5 Slide editor UX: template picker, per-slide editing with instant re-render
- [ ] 4.6 Export pipeline: standalone JSON structure and bundled HTML/JS package outputs

## Phase 5 — Document Studio (Stylized JSON/Markdown Viewer)

Build our own thin viewer shell composed from open-source rendering primitives (all MIT/Apache 2.0) — no third-party app embedding.

- [ ] 5.1 File-type detection + interception in the integrated browser: opening/navigating to `.md`, `.json`, `.yaml`, `.csv`, `.toml`, `.xml` renders the Document Studio view, with a toggle back to raw source (Monaco)
- [ ] 5.2 Markdown renderer: react-markdown (remark/rehype pipeline) with GitHub-flavored markdown, `@uiw/react-markdown-preview`-style base CSS, dark/light modes
- [ ] 5.3 Markdown extras: Shiki code-block highlighting, Mermaid diagram rendering, KaTeX math
- [ ] 5.4 Sanitization pipeline (rehype-sanitize) so untrusted markdown/HTML cannot XSS the host app
- [ ] 5.5 JSON tree inspector: collapsible tree with search, type badges, value previews, copy-as-path (`@uiw/react-json-view` or equivalent MIT component)
- [ ] 5.6 Interactive node-graph view for JSON/YAML/XML/CSV (evaluate embedding JSON Crack's Apache-2.0 graph engine vs. building on React Flow)
- [ ] 5.7 CSV/TSV renderer: PapaParse ingestion → sortable, filterable styled table
- [ ] 5.8 YAML/TOML support: parse (js-yaml / smol-toml) and route through the JSON tree + graph views
- [ ] 5.9 Theming system: user-selectable document themes (typography, spacing, palette) applied live; custom themes savable per workspace
- [ ] 5.10 Format conversion utilities: JSON ↔ YAML ↔ CSV ↔ XML
- [ ] 5.11 Export styled views to standalone HTML, PDF, and image
- [ ] 5.12 Performance: virtualized rendering for large files (multi-MB JSON, long markdown docs)

## Phase 6 — Agent Orchestration (Mission Control)

- [ ] 6.1 Agent runtime abstraction: spawn/monitor/terminate agent processes tied to project directories
- [ ] 6.2 Mission Control UI: agent roster, live status, activity feed per agent
- [ ] 6.3 Structured plan generation: agent proposes a step-by-step task list (file edits, commands, tests) as a typed schema
- [ ] 6.4 Plan review/approval flow: user validates or edits the plan before any filesystem or terminal execution
- [ ] 6.5 Execution engine: apply file edits, run terminal commands, stream logs to Mission Control
- [ ] 6.6 Multi-agent concurrency: isolation between agents in different project directories, conflict detection on shared paths
- [ ] 6.7 Task/plan persistence and resumability across app restarts

## Phase 7 — Autonomous Browser Control & Verification

- [ ] 7.1 Agent↔browser control bridge: navigate, click, type, complete forms, trigger DOM events on internal browser tabs
- [ ] 7.2 UI verification hooks: assert on DOM state, responsiveness checks across viewport sizes
- [ ] 7.3 Screenshot capture API for agents (full page + element-level)
- [ ] 7.4 Browser video recording of verification sessions
- [ ] 7.5 End-to-end flow: agent edits code → boots dev server → drives browser → validates UI (PRD flow 4.1)

## Phase 8 — Artifacts & Execution Reports

- [ ] 8.1 Artifact store: terminal logs, code diffs, screenshots, recordings, keyed to task/plan runs
- [ ] 8.2 Execution report generator: human-readable summary bundling artifacts for user review
- [ ] 8.3 Report viewer UI in Mission Control with drill-down to individual artifacts
- [ ] 8.4 Artifact retention/cleanup policy and disk-usage controls

## Phase 9 — Security & Permission Modes

- [ ] 9.1 Permission policy engine: central gate for file writes, terminal exec, and network/browser navigation
- [ ] 9.2 Secure Mode: read-only default; every file edit, command, and outbound request requires explicit confirmation
- [ ] 9.3 Review-Driven Mode: auto-approve workspace-bounded file writes; confirm terminal commands and external navigation
- [ ] 9.4 Agent-Driven Mode: autonomous execution within domain allowlists and designated project directories
- [ ] 9.5 Custom Mode: user-defined rules for shell permissions, URL access, and agent capability scopes (editable config UI)
- [ ] 9.6 Audit log of every permission decision and agent action
- [ ] 9.7 Threat-model review: proxy header-stripping scope, extension sandboxing, agent escape paths

## Phase 10 — Packaging, QA & Release

- [ ] 10.1 Electron packaging for macOS/Windows/Linux (electron-builder), code signing + notarization
- [ ] 10.2 Auto-update channel
- [ ] 10.3 Integration test suite: agent plan→approve→execute→verify happy path and permission-denial paths
- [ ] 10.4 Performance pass: startup time, memory with multiple browser tabs + agents
- [ ] 10.5 User documentation: getting started, permission modes, agent workflows, Document Studio
- [ ] 10.6 Tagged v0.1 release
