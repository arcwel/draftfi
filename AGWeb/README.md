# AGWeb — Agent-First Universal IDE & Browser

A unified, agent-first desktop workspace merging an autonomous AI development environment with a native Chromium browser. Users and autonomous agents create, inspect, execute, and verify web applications, interactive slides, and complex workflows from one "Mission Control" surface.

- **`PRD.md`** — product requirements (imported from the source Google Doc)
- **`TASKS.md`** — phased build task list with live status
- **`RESOURCES.md`** — complete inventory of techniques, databases, repos, and resources
- **`app/`** — the application (Electron + React + TypeScript + Tailwind, built with electron-vite)

## Architecture at a glance

Three Electron process tiers, strictly separated:

- **Main** (`app/src/main/`) — window lifecycle, single-instance lock, crash recovery, workspace/recent-projects persistence, native theme sync. All state writes are atomic JSON in `userData` (SQLite arrives with agent orchestration).
- **Preload** (`app/src/preload/`) — the only bridge into the renderer: a typed `window.agweb` API over `contextBridge`. Renderers run sandboxed with context isolation; no Node access.
- **Renderer** (`app/src/renderer/`) — the shell UI: sidebar (Projects/Agents), tabbed center stage (Welcome/Editor/Browser/Slides/Mission Control), bottom dock (Terminal/Logs), status bar. Zustand state, Tailwind styling, light/dark theming, and a keyboard-shortcut framework.

The IPC contract both sides compile against lives in `app/src/shared/ipc.ts`.

## Development

```bash
cd app
npm install
npm run dev        # launch with HMR
npm run typecheck  # strict TS across all three tiers
npm run build      # production bundles into out/
```

Smoke test (launches the built app, exercises the shell, saves a screenshot; use `xvfb-run -a` on headless machines):

```bash
npm run build && node scripts/smoke.mjs
```

## Status

Phase 1 (Application Shell & Window Management) is built and smoke-tested. See `TASKS.md` for the full roadmap: integrated Chromium browser tabs (Phase 2), IDE core (Phase 3), live preview + slides (Phase 4), Document Studio (Phase 5), agent orchestration (Phase 6+).
