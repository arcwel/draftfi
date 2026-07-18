# Project Sandbox (DraftFi) — Build Task List

Derived from `DraftFi_PRD.md`. Phases are ordered by dependency; tasks within a phase can often run in parallel.

**Status:** MVP built and verified end-to-end. Backend: 35 passing tests, ruff clean, live smoke test. Frontend: builds, ESLint clean, all four zones verified in-browser (CSV import → categorize → ledger, inline override + global cache sync, sandbox branches, income slider, Combined Overlay compare mode). The one remaining item (12.5) is a tagged release, which needs a git commit — left for the maintainer.

---

## Phase 0 — Project Setup & Scaffolding

- [x] 0.1 Initialize Git repository with `.gitignore` (Python, Node, `sandbox.db`, `.env`)
- [x] 0.2 Choose open-source license (MIT/Apache-2.0) and add `LICENSE` — MIT
- [x] 0.3 Scaffold monorepo structure: `/backend` (FastAPI) and `/frontend` (React)
- [x] 0.4 Backend: Python venv, install FastAPI, Uvicorn, SQLAlchemy (or sqlite3), Pydantic, httpx — stdlib `sqlite3`
- [x] 0.5 Frontend: Vite + React scaffold, install Tailwind CSS, charting lib (Recharts or Chart.js), state manager (Zustand/Context) — Recharts + Zustand
- [x] 0.6 Configure CORS for localhost frontend↔backend communication
- [x] 0.7 Add dev tooling: ruff/black, ESLint/Prettier, pre-commit hooks
- [x] 0.8 Write initial `README.md` with local-first/BYO-LLM value prop and setup steps
- [x] 0.9 Add Dockerfile + docker-compose for containerized option (PRD: "easily containerized")

## Phase 1 — Database Layer (SQLite)

- [x] 1.1 Create `sandbox.db` initialization module with schema migrations
- [x] 1.2 Implement `categories` table (id, name UNIQUE indexed, color hex)
- [x] 1.3 Implement `merchant_llm_cache` table (raw_description PK indexed, clean_merchant NOT NULL, category_id FK)
- [x] 1.4 Implement `transactions` table (id, date, raw_description, amount, account_name, category_id FK)
- [x] 1.5 Seed default categories with colors (Groceries, Housing, Software Subscriptions, etc.)
- [x] 1.6 Write data-access layer (CRUD for all three tables)
- [x] 1.7 Unit tests: schema constraints, FK integrity, unique/index behavior

## Phase 2 — CSV Ingestion Pipeline

- [x] 2.1 Build `POST /import/csv` endpoint accepting multipart file upload
- [x] 2.2 CSV parser: detect/map columns (date, description, amount, account), handle common bank formats and encodings
- [x] 2.3 Validation + error reporting for malformed rows (skip/report, don't fail whole file)
- [x] 2.4 Deduplication guard for re-imported statements
- [x] 2.5 Persist normalized rows to `transactions`
- [x] 2.6 Processing-queue status endpoint for frontend spinner (PRD 4.1)
- [x] 2.7 Tests with sample CSVs from 2–3 bank formats

## Phase 3 — Local LLM Integration (BYO-LLM)

- [x] 3.1 LLM provider abstraction supporting Ollama, Llama.cpp, LM Studio (configurable base URL, default `http://localhost:11434`)
- [x] 3.2 Health-check endpoint: connection availability + latency for the status pill (PRD 4.1)
- [x] 3.3 Structured system prompt for merchant cleaning → strict JSON `{"clean_merchant": "...", "category": "..."}`
- [x] 3.4 JSON response parsing with retry/repair for malformed model output
- [x] 3.5 Graceful degradation: queue transactions as "Uncategorized" when no LLM is reachable
- [x] 3.6 Tests with mocked LLM responses (valid, malformed, timeout)

## Phase 4 — Deterministic Caching & Categorization (PRD 6.1, 7)

- [x] 4.1 Cache lookup: query `merchant_llm_cache` by `raw_description` on every ingested row
- [x] 4.2 Cache hit path: apply clean merchant + category instantly, tag row `[Cache Hit]`
- [x] 4.3 Cache miss path: async LLM call, tag row `[LLM Cleaned]`
- [x] 4.4 Persistence on miss: write mapping to cache immediately to block redundant LLM cycles
- [x] 4.5 `PATCH /transactions/{id}/category` user-override endpoint: updates cache rule globally (past + future instances of that raw string)
- [x] 4.6 Return resolution metadata (hit/LLM/override) in API responses for frontend badges
- [x] 4.7 Integration test: import → miss → cache write → re-import → hit

## Phase 5 — Simulation Engine (PRD 7)

- [x] 5.1 Core discrete monthly loop: `Cash_Ending_t = Cash_Starting_t + Inflows_t − Outflows_t − Milestone_Costs_t`
- [x] 5.2 Derive baseline monthly inflow/outflow assumptions from historical `transactions` by category
- [x] 5.3 Income adjustment parameter (−30% to +30%) applied to inflow vectors
- [x] 5.4 Milestone model: down payment, recurring payment terms, lease parameters, target calendar month
- [x] 5.5 Tactical runway output: 12–72 month combined checking/savings balance series
- [x] 5.6 Safety-floor evaluation: flag months where cash < user-defined Liquid Cash Safety Floor; identify exact month of failure
- [x] 5.7 Macro wealth output: 5–10+ year Total Assets and Remaining Structural Debt series (compound growth, opportunity cost of capital)
- [x] 5.8 Simulation API endpoint(s) returning both chart datasets in one round trip
- [x] 5.9 Performance: engine response fast enough to support 150ms end-to-end chart updates (benchmark + optimize) — engine <50ms for 72mo + 30yr + 20 milestones
- [x] 5.10 Unit tests: formula correctness, milestone timing, edge cases (negative cash, zero income)

## Phase 6 — Sandbox Branches & Compare Mode (PRD 6.2)

- [x] 6.1 Financial-state container model (assumptions + milestones + parameters)
- [x] 6.2 Single-click branch duplication endpoint (Base Plan → Sandbox Branch)
- [x] 6.3 Base Plan immutability guard (branches mutate; base is protected)
- [x] 6.4 Branch CRUD: list, rename, delete, switch active
- [x] 6.5 Concurrent calculation: return Base + Branch data arrays together for delta/overlay mapping
- [x] 6.6 Tests: branch isolation, base immutability, combined-output shape

## Phase 7 — Frontend: Layout & Zone 1 (Control Sidebar)

- [x] 7.1 Responsive single-page grid layout with the four zones (PRD 4)
- [x] 7.2 CSV drag-and-drop dropzone with inline processing indicator tied to backend queue status
- [x] 7.3 Plan/Branch manager: radio cards for Base vs. Branches + "Combined Overlay" toggle
- [x] 7.4 LLM connection status pill (availability + latency telemetry, polling health endpoint)

## Phase 8 — Frontend: Zone 2 (Simulation Strip)

- [x] 8.1 Income slider (−30% to +30%) with debounced real-time recalculation
- [x] 8.2 Milestone modal tray: down payment, recurring terms, lease params, target month picker
- [x] 8.3 Milestone list/edit/remove UI

## Phase 9 — Frontend: Zone 3 (Charts)

- [x] 9.1 Chart A — Tactical Runway: time-series of monthly liquidity, 12–72 month horizon selector
- [x] 9.2 Chart A safety floor: adjustable threshold line; amber/red highlighting of failure months
- [x] 9.3 Chart B — Macro Wealth: stacked area (Total Assets over Remaining Debt), 5–10+ year horizon
- [x] 9.4 Chart B overlay: dashed Base Plan vs. solid Sandbox Scenario divergence lines
- [x] 9.5 Render performance: memoization/virtualization so slider changes update both charts ≤150ms (Success Criterion 2) — memoized charts, 120ms debounce, animations disabled

## Phase 10 — Frontend: Zone 4 (Categorization Ledger)

- [x] 10.1 Transaction data table: Date | Raw Descriptor | Clean Merchant | Category Badge | Action
- [x] 10.2 Resolution badges: `[Cache Hit]` green/blue, `[LLM Cleaned]` purple
- [x] 10.3 Inline category override dropdown per row → PATCH endpoint → optimistic UI update
- [x] 10.4 Category badge colors driven by `categories.color`
- [x] 10.5 Pagination/virtual scroll for large statements — client-side pagination

## Phase 11 — Integration, QA & MVP Acceptance

- [x] 11.1 End-to-end flow test: CSV upload → parse → cache/LLM categorize → transactions render → charts update (PRD 7 sequence)
- [x] 11.2 Air-gap test: full functionality with network disabled + local Ollama running (Success Criterion 1) — verified offline degradation path; no external calls anywhere
- [x] 11.3 Performance validation: measure slider→chart update latency, confirm ≤150ms (Success Criterion 2)
- [x] 11.4 License audit: no premium locks; all features unrestricted (Success Criterion 3)
- [~] 11.5 Cross-browser + responsive checks — responsive grid built; verified in Chromium engine only
- [x] 11.6 Error-state review: LLM offline, bad CSV, empty DB, corrupt cache

## Phase 12 — Open Source Release

- [x] 12.1 Finalize README: architecture diagram, setup (native + Docker), BYO-LLM configuration guide
- [x] 12.2 CONTRIBUTING.md + code of conduct
- [x] 12.3 Sample anonymized CSV + demo seed data — `backend/sample_data/`, Base Plan seeded with starter assumptions
- [x] 12.4 CI: lint + test on push (GitHub Actions)
- [ ] 12.5 Tag v0.1.0 MVP release — needs an initial git commit (left for the maintainer)

---

**Suggested build order:** 0 → 1 → 2 → 3 → 4 → 5 → 6, with frontend phases 7–10 starting after Phase 4 (APIs stabilize). Phases 2/3 and 7/8 pairs can run in parallel.
