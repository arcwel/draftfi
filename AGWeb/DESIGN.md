# AGWeb Design Direction — Browser-First & the Dev Deck

Design canvas (mockups + interactive reveal prototype): https://claude.ai/code/artifact/aeb15107-803d-4e35-a6f2-25293afddcbc
Working design sources live in `design/` (`*.dc.html` + `canvas.json`).

## Principles

1. **The browser is the product.** Default state is a pure browser: tab strip, toolbar, page. Zero dev chrome. AGWeb must be a great daily browser before it is anything else.
2. **Development is a summonable layer.** All IDE features live in the **Dev Deck** — think Chrome DevTools, but the panels are IDE features. One gesture (`⌘D` / Deck button) reveals it; the same gesture puts it away completely.
3. **Every dev feature is an independent block.** Editor, Terminal, Files, Agents (Mission Control), Logs, Slides — each is a self-contained block that can be hidden, shown, resized, docked anywhere, floated, or collapsed to a rail, independently of the others.

## The Deck reveal (signature animation)

Direction A — "Stage" (the recommended default, prototyped on the canvas):

- The page **scales back into a spotlit stage**: full-bleed viewport animates to a rounded, bordered frame with a soft sky glow and shadow — the page becomes the *subject under inspection*.
- Dev blocks **slide in staggered**: right column (Editor, Files) enters ~70 ms after the stage starts moving; bottom dock (Terminal, Agents) ~140 ms after. Reverse order on hide.
- Timing: 550 ms, easing `cubic-bezier(0.32, 0.72, 0, 1)` (fast start, long settle). A viewport chip ("localhost:5173 · inspecting") fades in on the stage once it lands.
- Direction B — "Overlay": glass blocks (blurred translucent panels) float over the dimmed page. Kept as an alternate: it is also the natural rendering of *floating* blocks within Direction A, so the two compose rather than compete.

## Block anatomy

Header: drag grip · identity + context (file / shell / agent) · float/re-dock · collapse-to-rail · close. Resize handles on every edge.

Block states:

- **Docked** — snapped into the right column or bottom dock; shares space with neighbors.
- **Floating** — glass panel over the page; free position/size, always on top.
- **On the rail** — collapsed to an icon on the window edge; one click restores it exactly where it was.
- **Closed** — reopen from the Deck menu.

**Presets:** Browsing (deck hidden) · Building (stage + editor/terminal) · Debugging (stage + terminal/logs/agents). One keystroke swaps the whole layout. Layouts and presets persist per project.

## Visual language

Matches the existing shell: `#0b0f14` app ground, `#0e1420` panels, `#1e293b` borders, slate text ramp (`#e2e8f0` / `#94a3b8` / `#64748b`), sky accent (`#38bdf8` on dark, `#0284c7` fills), 10 px block radii, `ui-sans-serif` UI + `ui-monospace` code, 11 px uppercase block titles with 0.06 em tracking. Floating blocks: `rgba(14,20,32,0.88)` + 14 px backdrop blur + `0 24px 56px` shadow.

## Implementation notes

- The stage is the existing `WebContentsView`. During the reveal, the renderer animates the stage placeholder with CSS while the existing ResizeObserver → `setBounds` pipe streams bounds to the native view each frame; if IPC jitter shows, fall back to hiding the view behind a captured snapshot for the 550 ms flight and snapping bounds at the end.
- Deck state machine lives in the shell store: `deck: hidden | revealed`, per-block `{ zone: right | bottom | floating | rail | closed, order, size, floatRect }`, persisted per project.
- Blocks are the unit of extension: agent-generated panels (execution reports, diffs) arrive as blocks later.
