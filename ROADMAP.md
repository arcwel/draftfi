# DraftFi Roadmap

Remaining features, grouped into batches that touch the same code areas so each
batch can be built with minimal cross-branch churn. Order within a batch is the
suggested build order; batches are largely independent of each other.

**Already shipped** (for context): CSV import (additive, dedup, live progress),
multi-provider BYO-LLM categorization with batching + cache, natural-language
scenario input, monthly budget with targets + scenario impact, dual forecast
charts, sandbox branches + compare, manual transaction CRUD, sync with
progress, export/backup/restore, reset, one-click desktop app.

---

## Batch A — LLM provider surface
*Code: `services/llm.py`, `services/llm_config.py`, `api/llm_status.py`, `components/LLMConfigPanel.jsx`*

- [ ] A1. **"Test connection" button** — validate the pasted key/endpoint on
      demand with a clear pass/fail message (reuses `llm.health`).
- [ ] A2. **Model picker dropdown** — fetch the provider's live model list
      (Ollama `/api/tags`, OpenAI `/models`, Anthropic/Gemini model endpoints)
      with free-text fallback.
- [ ] A3. **Subscription / recurring-charge detection** — flag merchants that
      recur at regular intervals & amounts; "Subscriptions: $61/mo" chip in the
      budget panel. (Heuristic first, LLM assist optional.)
- [ ] A4. **Monthly insights summary** — optional LLM-generated narrative of
      notable changes ("Dining up 40% vs. your 3-month average").

## Batch B — Import pipeline
*Code: `services/csv_parser.py` (+ new parsers), `services/ingestion.py`, `api/imports.py`, `components/Dropzone.jsx`*

- [ ] B1. **OFX/QFX/QIF support** — parse the other common bank export formats
      through the same dedupe/categorize pipeline.
- [ ] B2. **Column-mapping memory + manual mapping UI** — remember each bank's
      header layout (keyed by header signature, stored in `app_settings`);
      when detection fails, show a "map your columns" dialog instead of erroring.
- [ ] B3. **Multi-file import** — accept multiple dropped files / a folder;
      one job with combined progress.

## Batch C — Ledger & categories
*Code: `api/transactions.py`, `db/repository.py` (+ migration), `zones/Ledger.jsx`, new `CategoryManager`*

- [ ] C1. **Server-side search/sort/pagination** — query params (`q`, `sort`,
      date range) on `/transactions`; ledger stops loading a fixed 500 rows.
- [ ] C2. **Split transactions** — divide one row across categories
      (migration: `parent_tx_id` or a `transaction_splits` table).
- [ ] C3. **Notes & tags per transaction** (migration: `note` column, `tags`).
- [ ] C4. **Category management UI** — create/rename/recolor/merge/delete
      categories (merge re-points transactions + cache rules).

## Batch D — Budget analytics
*Code: `services/budget.py`, `api/budget.py`, `components/BudgetPanel.jsx` (+ new chart component)*

- [ ] D1. **Month-over-month trends** — per-category monthly series endpoint +
      trend chart (bar/line) alongside the averages.
- [ ] D2. **Specific-month view** — month picker on the budget panel
      ("show me March") instead of all-time averages only.
- [ ] D3. **Income vs. spend cash-flow chart** — actuals over time,
      complementing the forward-looking forecast.
- [ ] D4. **Budget rollover option** — unspent budget carries into the next
      month (per-category toggle).

## Batch E — Simulation engine
*Code: `services/simulation.py`, `models/schemas.py`, `api/simulation.py`, chart components, `MilestoneModal.jsx`*

- [ ] E1. **Proper loan amortization** — split recurring payments into
      interest + principal from `annual_debt_rate_pct`; debt payoff and net
      worth become realistic for mortgages/auto loans.
- [ ] E2. **Income/expense change events** — "raise to $X at month N",
      "expenses drop $Y at month M" (new event list beside milestones).
- [ ] E3. **Inflation adjustment** — optional real-terms toggle on the macro
      chart.
- [ ] E4. **Multi-branch compare** — overlay 3+ scenarios plus a delta table
      (base vs. branches at months 12/36/72).
- [ ] E5. **Goal tracking** — target net worth/cash by date, with an
      on/off-track indicator derived from the active scenario.

## Batch F — Desktop app
*Code: `backend/desktop.py`, `packaging/build.py`, `.github/workflows/release.yml`*

- [ ] F1. **In-app update check** — poll GitHub Releases on launch; toast
      "v0.3.0 available" linking to the download.
- [ ] F2. **Single-instance guard + tray/menu-bar icon** — reopening the app
      focuses the existing window; quick-quit from the tray.
- [ ] F3. **Linux build** — PyInstaller on `ubuntu-latest` in the release
      matrix (tarball; webview falls back to the browser where WebKitGTK is
      absent), published as `DraftFi-linux.tar.gz`.

## Batch G — Security & quality
*Code: `services/llm_config.py`, `db/`, `frontend/src/lib/format.js` (new), CI, frontend tests*

- [ ] G1. **Encrypt stored API keys** via OS keychain (Keychain/DPAPI through
      `keyring`), with plaintext fallback for headless/dev.
- [ ] G2. **Optional app passcode** — local lock screen gating the UI.
- [ ] G3. **Frontend tests** — Vitest + store/component coverage, wired into CI
      (backend has 70 tests; frontend has none).
- [ ] G4. **Currency/locale setting** — one setting replacing the hardcoded
      `USD`/`en-US` in 5 components (shared `format.js` helper).

---

**Suggested order:** C (daily-use depth) → B (import breadth) → D (analytics) →
E (engine fidelity) → A (LLM polish) → F (desktop polish) → G (hardening).
G3/G4 are cheap and can ride along with any batch.

*Explicitly out of scope (owner decision): code signing, Intel-Mac build,
onboarding tour, light theme.*
