# AGWeb — Agent-First Universal IDE & Browser — Build Task List

Derived from `AGWeb/PRD.md`. Phases are ordered by dependency; tasks within a phase can often run in parallel.

**Status:** Phase 1 complete; Phase 2 core browser working. Integrated Chromium tabs (WebContentsView) with navigation chrome, per-tab process isolation, DevTools, default-deny permissions, and popup→new-tab handling are in and covered by the smoke test (navigates a page via the address bar and verifies the title round-trips into the tab strip). Lint (ESLint+Prettier) and CI (`.github/workflows/agweb.yml`: lint → typecheck → build → xvfb smoke) are in place. See `RESOURCES.md` for the full techniques/repos/resources inventory.

---

## Phase 0 — Project Setup & Scaffolding

- [x] 0.1 Initialize project structure inside `AGWeb/` with `.gitignore` (Node, Electron build output, Python, `.env`)
- [x] 0.2 Choose and document open-source license consistent with Electron/Chromium/Code - OSS dependencies — MIT (inherits repo `LICENSE`)
- [x] 0.3 Scaffold Electron + TypeScript + React app (main process, preload, renderer) with Vite bundling — electron-vite under `app/`
- [x] 0.4 Add Tailwind CSS and base design tokens for the Mission Control shell — Tailwind v4
- [ ] 0.5 Integrate Monaco Editor as the embedded code editor component (moved to Phase 3 editor work)
- [ ] 0.6 Set up Python tooling workspace (`backend/` or `tools/`) with venv, ruff, pytest — deferred until the first Python service lands (Phase 6 agent runtime / Phase 2.5 proxy)
- [x] 0.7 Dev tooling: ESLint (flat config + typescript-eslint + react-hooks), Prettier, TypeScript strict mode — `npm run lint` / `npm run format` (pre-commit hooks still open)
- [x] 0.8 CI pipeline: `.github/workflows/agweb.yml` — lint, typecheck, build, and Electron smoke test under Xvfb on every AGWeb push/PR
- [x] 0.9 Write `AGWeb/README.md` with vision, architecture overview, and dev setup steps

## Phase 1 — Application Shell & Window Management

- [x] 1.1 Electron main-process architecture: window lifecycle, single-instance lock, crash recovery — bounded renderer auto-reload, window-state persistence clamped to attached displays
- [x] 1.2 Multi-pane layout shell: sidebar (projects/agents), tabbed center stage (editor / browser / slides), bottom dock (terminal / logs) — plus status bar; later-phase panes are placeholders
- [x] 1.3 Secure IPC contract between main, preload, and renderer — typed `window.agweb` API in `src/shared/ipc.ts`; contextIsolation + sandbox on, nodeIntegration off, strict CSP
- [x] 1.4 Cross-window communication layer using PostMessage/Postmate for embedded previews — `PreviewChannel` handshake protocol with origin pinning (`src/renderer/src/preview/messaging.ts`)
- [x] 1.5 Workspace/project model: open folder, recent projects, per-project state persistence — atomic JSON stores in `userData`; richer per-project UI state grows with Phases 2–3
- [x] 1.6 Theming (light/dark) and keyboard-shortcut framework — persisted theme synced to nativeTheme; registry-based shortcuts (`mod+b/j/t/w`, `mod+shift+l`) listed on the Welcome view

## Phase 2 — Integrated Browser (Chromium)

- [x] 2.1 Embed Chromium browser tabs via Electron `WebContentsView` with standard navigation chrome — back/forward/reload/stop, URL bar with search fallback, live title/loading state pushed over IPC (`src/main/browser.ts`, `BrowserPane.tsx`)
- [ ] 2.2 Tab management: open/close ✅ (per-tab process isolation via sandboxed views in a dedicated `persist:agweb-browser` session); reorder and session restore still open
- [x] 2.3 DevTools access per tab (detached window via toolbar button)
- [ ] 2.4 Chrome extension loading support (Manifest V3 via Electron's extensions API; document limitations)
- [ ] 2.5 Local proxy layer that strips frame-busting headers (X-Frame-Options, CSP frame-ancestors) for development-preview embedding only
- [ ] 2.6 Proxy safety rails: enabled only for allowlisted dev origins, clear UI indicator when active
- [ ] 2.7 Download handling and permission prompt UI still open; web permissions currently default-deny, popups open as new shell tabs

## Phase 2B — Browser-First Shell & Dev Deck (see `DESIGN.md`)

- [x] 2B.1 Browser-only default mode: pure browser chrome (tab strip + toolbar + Deck button), start page on empty tabs, no dev UI visible — old sidebar/center-tabs/status-bar shell removed
- [x] 2B.2 Deck reveal/hide animation (`⌘D` / Deck button): stage retreat + staggered block entrance per DESIGN.md (0.55s, 70/140ms offsets); WebContentsView bounds streamed each animation frame via ResizeObserver, native corner radius synced to the stage frame
- [x] 2B.3 Block system: independent block instances in groups with header (grip, tabs, `+`, float placeholder, close) — edge resize still open
- [x] 2B.4 Drag-and-drop rearrangement: drag tabs (blocks) or grips (whole stacks); drop on a header to stack, on a group to insert before it, on zone space to append/split; drop targets highlight — floating drops arrive with 2B.7/2B.10
- [x] 2B.5 Rail: collapse blocks to an icon strip on the right edge (stage/columns shift to make room); one click restores to the block's previous zone
- [x] 2B.6 Layout presets (Browsing / Building / Debugging) via the toolbar Layout menu + per-project layout persistence (localStorage keyed by workspace path, debounced saves, restored on project switch)
- [x] 2B.7 Floating blocks: a group's float button pops the stack into its own frameless child window over the page (native browser views paint above renderer DOM, so floats are real OS windows); header drags the window, Dock returns the group to the browser window
- [x] 2B.8 Tabbed stacks: groups are tabbed stacks; `+` opens a new instance into the group; drag a tab onto a header to stack, drag it out to split; closing the last tab removes the group
- [x] 2B.9 Multiple instances per block type (Terminal 1/2, Editor 2…); instance lifecycle + naming
- [x] 2B.10 Detached mode: the toolbar pop-out sends the whole deck into a standalone frameless IDE window (blocks laid out IDE-style); the browser reverts to pure browsing with a "Deck detached" indicator (⌘D focuses the deck window); "Dock back" or closing the window re-merges into the Stage layout. Deck layout is mirrored across all shell windows via a main-process broadcast bus (stale-boot-state guard included)

## Phase 3 — IDE Core (Editor, Files, Terminal)

- [x] 3.1 File explorer: lazy tree of the workspace with create/rename (inline)/delete (confirmed) and recursive-watcher refresh; workspace-scoped path validation in main — move-via-drag still open
- [x] 3.2 Monaco integration: bundled workers (JSON/CSS/HTML/TS IntelliSense), syntax highlighting incl. Python/Markdown/YAML, shared document models, tabbed open files synced across windows, dirty markers, ⌘S save-to-disk
- [x] 3.3 Formatter integration: Prettier (lazy-loaded) for JS/TS/JSON/CSS/HTML/Markdown/YAML via the editor's Format button / ⇧⌥F — ruff/black join the Python tooling workspace (0.6)
- [x] 3.4 Integrated terminal: node-pty sessions in main (in-process when rebuilt for Electron, system-node pty-host fallback otherwise) + xterm.js frontend; sessions keyed by block id survive deck hide/move/detach with scrollback replay; multiple sessions via `+`
- [x] 3.5 Diff viewer: Monaco side-by-side diff overlay in the editor (saved-on-disk vs live buffer) — the same component agents' proposed-change review will reuse
- [x] 3.6 Search across project: ripgrep-backed (JSON stream, gitignore-aware) with a pure-Node fallback; Search block added via the toolbar's + Block menu, hits jump to file+line in the editor

## Phase 4 — Live Preview & Slide Runtime

- [ ] 4.1 Dev-server manager: detect/boot local dev servers per project, port allocation, health checks
- [ ] 4.2 Live preview pane with hot-reload wired to file changes
- [ ] 4.3 Style isolation for embedded previews (Shadow DOM / CSS Modules) so host UI and preview don't bleed
- [ ] 4.4 Reveal.js slide runtime: render decks from project files in a synchronized preview pane
- [ ] 4.5 Slide editor UX: template picker, per-slide editing with instant re-render
- [ ] 4.6 Export pipeline: standalone JSON structure and bundled HTML/JS package outputs

## Phase 5 — Document Studio (Stylized JSON/Markdown Viewer)

Build our own thin viewer shell composed from open-source rendering primitives (all MIT/Apache 2.0) — no third-party app embedding.

- [x] 5.1 Doc-type files (`.md/.json/.yaml/.yml/.toml/.csv/.tsv`) open as Document Studio tabs in the browser tab strip with a Styled ⇄ Source (editable Monaco, ⌘S) toggle and Open-in-Editor; views live-refresh on disk changes — intercepting *navigated* URLs joins the Phase 2.5 proxy work
- [x] 5.2 Markdown renderer: react-markdown + remark-gfm with GitHub-flavored styling (tables, task lists, blockquotes, code), light/dark
- [x] 5.3 Markdown extras: code-block highlighting (highlight.js via rehype-highlight; Shiki noted as an upgrade path), Mermaid diagrams (lazy-loaded, securityLevel strict), KaTeX math — all downstream of the sanitize pass
- [x] 5.4 Sanitization pipeline (rehype-sanitize) so untrusted markdown/HTML cannot script in the host app
- [x] 5.5 JSON tree inspector: collapsible tree with search (filters to matching subtrees), type badges (object/array counts), value previews, hover copy-as-path
- [x] 5.6 Interactive node-graph view for JSON/YAML/TOML: own lightweight SVG engine (~250 lines, no graph deps) — containers as nodes listing scalar fields, left-to-right tree layout, drag-pan, wheel-zoom, click-to-collapse subtrees, 1200-node truncation notice; Graph segment in the Studio toggle
- [x] 5.7 CSV/TSV renderer: PapaParse → sortable (numeric-aware), filterable table with sticky header
- [x] 5.8 YAML/TOML support: js-yaml / smol-toml parse, routed through the JSON tree (graph view pending 5.6)
- [x] 5.9 Theming: Default / Serif / Compact document themes applied live, saved per workspace — free-form custom themes can layer on later
- [x] 5.10 Format conversion: JSON ↔ YAML ↔ TOML and CSV ↔ JSON from the Studio's Convert menu; writes a sibling file and opens it (XML joins with 5.6's XML support)
- [x] 5.11 Export: Markdown views to standalone HTML and PDF (hidden-window print) with embedded theme CSS; any styled view to PNG (stage capture); native save dialogs
- [x] 5.12 Virtualized rendering: JSON tree flattens visible nodes and windows the viewport; CSV table windows rows — display caps removed, multi-MB files stay responsive

## Phase 6 — Agent Orchestration (Mission Control)

- [x] 6.1 Agent runtime abstraction: sessions spawned/monitored/stopped in the main process, bound to the open workspace (`src/main/agent.ts`; Claude `claude-opus-5`, mock provider via `AGWEB_AGENT_MOCK=1` for offline testing)
- [x] 6.2 Mission Control UI: session roster with live status badges, per-session activity feed, per-edit before/after diff viewer (Agents block); merged live feed across sessions (Logs block)
- [x] 6.3 Structured plan generation: forced `create_plan` tool call with a strict typed schema (step kind/title/detail)
- [x] 6.4 Plan review/approval flow: plans held in `awaiting_approval` until Approve & run / Reject — no filesystem or terminal execution before approval (plan editing still open)
- [x] 6.5 Execution engine: manual tool-use loop over workspace-scoped tools (read/write/list/search/run_command), every action streamed to Mission Control; refusal + pause_turn handling, stop button
- [ ] 6.6 Multi-agent concurrency: several sessions can run at once ✅; per-directory isolation and conflict detection on shared paths still open
- [x] 6.7 Task/plan persistence across app restarts (atomic JSON store; sessions interrupted mid-run are marked as errored on boot — mid-run resume still open)

## Phase 7 — Autonomous Browser Control & Verification

- [x] 7.1 Agent↔browser control bridge (`src/main/agent-browser.ts`): `browser_open/navigate/click/type/wait_for` tools drive real shell tabs — the view is created in main and adopted into the tab strip so the user watches the agent work live; typing dispatches input/change events for framework-bound inputs
- [x] 7.2 UI verification hooks: `browser_read` (page/element text) and `browser_eval` (arbitrary DOM assertions as JSON) + `browser_set_viewport` responsiveness emulation via Chromium device emulation (mobile/desktop, reset with 0×0)
- [x] 7.3 Screenshot capture API: `browser_screenshot` saves full-page or element-level PNGs to workspace-relative paths, logged to Mission Control as screenshot entries
- [ ] 7.4 Browser video recording of verification sessions
- [x] 7.5 End-to-end flow validated in the smoke test (mock provider): agent writes a file → opens a tab → clicks → asserts the DOM updated → types and reads the value back → captures screenshot evidence on disk (PRD flow 4.1; a real dev-server run needs a live model)

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
