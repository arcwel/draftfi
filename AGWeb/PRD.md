# Product Requirements Document: Agent-First Universal IDE & Browser (AGWeb)

> Source: [Google Doc PRD](https://docs.google.com/document/d/1pCAo4R_vbRcJ5uXrgp8Th4UGSBbCL3lFAPpqYj4wQ64/edit?usp=drivesdk), imported 2026-08-27.

## 1. Executive Summary & Architecture Overview

This platform is a unified, agent-first desktop workspace that merges an autonomous AI development environment with a native, unrestricted Chromium web browser. Built on open-source foundations (Code - OSS, Electron, Chromium), the platform functions as a "Mission Control" where users and autonomous agents can create, inspect, execute, and verify web applications, interactive slides, and complex workflows.

## 2. Core Dependencies & Source Repositories

| Component | Library / Framework | Official URL |
| :-- | :-- | :-- |
| **Desktop Runtime** | Electron | <https://www.electronjs.org> |
| **Core Browser Engine** | Chromium Project | <https://www.chromium.org> |
| **IDE Base** | Code - OSS (VSCodium) | <https://vscodium.com> / <https://github.com/microsoft/vscode> |
| **Code Editor Component** | Monaco Editor | <https://microsoft.github.io/monaco-editor> |
| **Frontend Framework** | React | <https://react.dev> |
| **Language & Typings** | TypeScript | <https://www.typescriptlang.org> |
| **Backend & Tooling** | Python | <https://www.python.org> |
| **Presentation Engine** | Reveal.js | <https://revealjs.com> |
| **Styling Framework** | Tailwind CSS | <https://tailwindcss.com> |
| **Cross-Window Comm** | Postmate / PostMessage API | <https://github.com/dollarshaveclub/postmate> |

## 3. Key Features & Functional Requirements

### Mission Control & Agent Orchestration

- **Multi-Agent Coordination:** Concurrently spawn, monitor, and manage autonomous agents across different project directories.
- **Dynamic Task Planning:** Agents generate structured execution plans for user validation before executing filesystem changes or terminal commands.
- **Artifact Generation:** Autonomous production of tangible proofs of work, including terminal logs, code diffs, screenshot captures, and browser video recordings.

### Universal Web Browser & Sandbox Execution

- **Full Chromium Capabilities:** Integrated browser tab supporting full extensions, standard navigation, DevTools, and native rendering.
- **Zero-Friction Embedding:** Integrated proxy layer to strip frame-busting headers (X-Frame-Options, strict CSPs) and resolve cross-origin issues for development previews.
- **Autonomous Browser Control:** Direct agent hooks to navigate pages, complete forms, trigger DOM events, and validate UI responsiveness.

### Integrated Development Environment (IDE)

- **Code & Schema Editing:** Native code editing with full syntax highlighting, IntelliSense, and formatters for JSON, HTML, CSS, JavaScript, and Python.
- **Live Preview & Slide Runtime:** Direct embedding of Reveal.js decks and custom web apps with hot-reloading and isolated styling (CSS Modules/Shadow DOM).

## 4. User Interaction Flows

### Autonomous Task Execution & Browser Verification

1. User provides a prompt or feature request via the Mission Control interface.
2. The agent generates a step-by-step task list detailing file edits and testing steps.
3. Upon user approval, the agent applies the code modifications.
4. The agent boots the local development server and navigates the internal Chromium browser to verify UI interactions.
5. An execution report containing screenshots and screen recordings is delivered to the user for review.

### Manual Web Browsing & Slide Development

1. User accesses the unified browser view to interact with external sites or local apps without IDE overhead.
2. User opens the integrated presentation editor to draft slides using Reveal.js templates.
3. Changes render instantly in a synchronized preview pane.
4. Projects can be exported directly as standalone JSON structures or bundled HTML/JS packages.

## 5. Security & Permission Modes

- **Secure Mode:** Read-only system access; every file edit, terminal execution, and outbound network request requires explicit manual confirmation.
- **Review-Driven Mode:** Filesystem writes within workspace bounds are auto-approved; terminal commands and external browser navigations require confirmation.
- **Agent-Driven Mode:** Autonomous execution within pre-configured domain allowlists and designated project directories.
- **Custom Mode:** User-defined rules governing shell permissions, URL access, and agent capability scopes.
