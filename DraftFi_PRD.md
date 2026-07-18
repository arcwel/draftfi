# Product Requirements Document (PRD)
## Project Sandbox: Local-First Financial Simulation Engine

### 1. Objective & Value Proposition
**Project Sandbox** is an open-source, local-first personal financial forecasting application designed for forward-looking **"What-If" scenario modeling**. 

Unlike commercial alternatives that require invasive, fragile bank syncing APIs and raise privacy concerns, Project Sandbox processes all financial data locally on the user's machine. By leveraging a **Bring Your Own LLM (BYO-LLM)** paradigm, the application enables automated transaction cleaning, intelligent spending categorization, and natural language simulation inputs with zero external data leaks.

---

### 2. System Architecture & Tech Stack
To ensure a robust, maintainable, and easily containerized open-source ecosystem, the application uses a completely decoupled architecture:

*   **Frontend:** React with Tailwind CSS for an interactive, responsive dashboard presentation layer.
*   **Backend:** Python (FastAPI) to run the simulation math, process local data, and manage local LLM integrations.
*   **Database:** SQLite (`sandbox.db`), living completely client-side to persist transaction data, historical states, and categorization caches.
*   **AI Layer:** Local inference engines (e.g., Ollama, Llama.cpp, or LM Studio) exposed via local localhost endpoints (e.g., `http://localhost:11434`).

---

### 3. Database Schema Design (Local Cache & Transaction Layer)
To maximize local performance and prevent redundant local LLM queries, SQLite acts as both a datastore and an intelligent caching mechanism.

#### 3.1 `categories` Table
Defines user-controlled budget and spending classifications.
*   `id` (INTEGER, Primary Key)
*   `name` (TEXT, Unique, Indexed) — *e.g., "Groceries", "Software Subscriptions", "Housing"*
*   `color` (TEXT) — *Hex code for frontend data visualizations (e.g., "#3B82F6")*

#### 3.2 `merchant_llm_cache` Table
Maps messy, raw bank descriptor strings to cleaned merchant entities and assigned categories.
*   `raw_description` (TEXT, Primary Key, Indexed) — *e.g., "AMZN MKTP US\*2A34M1 BILLING"*
*   `clean_merchant` (TEXT, Nullable=False) — *e.g., "Amazon"*
*   `category_id` (INTEGER, Foreign Key referencing `categories.id`)

#### 3.3 `transactions` Table
Stores historical normalized transaction baselines used to inform future spending assumptions.
*   `id` (INTEGER, Primary Key)
*   `date` (TEXT/DATE, Nullable=False)
*   `raw_description` (TEXT, Nullable=False)
*   `amount` (REAL, Nullable=False)
*   `account_name` (TEXT, Nullable=False) — *e.g., "Chase Checking"*
*   `category_id` (INTEGER, Foreign Key referencing `categories.id`)

---

### 4. React Frontend Dashboard Interface Layout
The user interface utilizes a high-density, single-page responsive workspace structured into **four core functional grid sections** to keep all variables and visual feedbacks visible at a single glance.

```
+------------------------------------------------------------------------------------------------+
|                                  PROJECT SANDBOX UI WORKSPACE                                  |
+-------------------+----------------------------------------------------------------------------+
|                   | ZONE 2: INTERACTIVE SIMULATION STRIP (TOP BAR)                             |
|                   | [Income Slider: -30% <> +30%]   [+ Add New Milestone / Large Purchase]     |
| ZONE 1:           +----------------------------------------------------------------------------+
| CONTROL SIDEBAR   | ZONE 3: VISUAL SIMULATION GRID (CENTER STAGE)                              |
|                   |                                                                            |
| - CSV Drag-Drop   |   [CHART A: Tactical Cash Runway View]   ---> (12-72 Month Liquidity Timeline) |
| - Branch Toggles  |                                                                            |
|   (Base vs. Exp)  |   [CHART B: Macro Wealth Compound View]  ---> (5-10+ Year Total Net Worth) |
| - Local LLM Status+----------------------------------------------------------------------------+
|                   | ZONE 4: CATEGORIZATION LEDGER (BOTTOM PANEL)                               |
|                   | [Date] | [Raw Descriptor] | [Clean Merchant] | [Category Badge] | [Action] |
+-------------------+----------------------------------------------------------------------------+
```

#### 4.1 Zone 1: Structural Left Control Sidebar
*   **Data Ingest Dropzone:** A drag-and-drop landing area supporting raw bank statement CSV files. Spins an inline processing indicator tied directly to the FastAPI processing queue when parsing.
*   **Plan/Branch Manager:** Radio card buttons allowing the user to seamlessly switch between the static **Base Plan** and any active **Sandbox Branches** or toggle a "Combined Overlay" comparison view.
*   **LLM Connection State:** A telemetry status pill showing connection speed and availability of local localhost inference providers (e.g., Ollama).

#### 4.2 Zone 2: Dynamic Simulation Parameter Strip (Top Bar)
*   **Variable Income Adjustment Slider:** A continuous slider allowing immediate real-time modifications from -30% to +30%. Shifting this value immediately recalculates the incoming cash velocity vectors inside the engine.
*   **Milestone Trigger Interface:** A button launching a modal configuration tray to inject high-ticket items. Inputs include: Down Payment amount, regular recurring payment terms, lease parameters, and specific calendar target months.

#### 4.3 Zone 4: Transaction Categorization Ledger (Bottom Panel)
*   A clean data table rendering newly parsed statement transactions.
*   **Metadata Badges:** Visual tags showing how each row was resolved: `[Cache Hit]` (rendered in green/blue) indicates a local SQLite database match, while `[LLM Cleaned]` (rendered in purple) highlights a fresh local inference pass.
*   **Inline Override Action:** Dropdown selection tools on every row that let users change categories, instantly triggering a local backend database write to update the mapping cache rules globally.

---

### 5. Dual-View Visualization Specifications

#### 5.1 Chart A: The Tactical Runway View (12 - 72 Months Horizon)
*   **Focus:** Mid-term cash flow survival limits, liquidity drawdowns, and systemic structural overhead timing bottlenecks.
*   **UI Component:** A high-resolution time-series chart plotting the baseline combined checking/savings balances month-by-month.
*   **Alert Threshold Logic:** Integrates a user-adjustable "Liquid Cash Safety Floor". If an experimental sandbox scenario causes the cash line to drop below this line, the system colors that section of the timeline amber or flashing red to pinpoint the exact month of failure.

#### 5.2 Chart B: The Macro Wealth View (5 - 10+ Years Horizon)
*   **Focus:** Compound growth vectors, structural asset expansion metrics, and the true opportunity cost of cash capital expenditures.
*   **UI Component:** A long-range stacked area chart rendering Total Assets stacked above Remaining Structural Debt.
*   **Simulation Impact:** Superimposes a dashed line (Base Plan) over a solid line (Sandbox Scenario) to display the multi-decade wealth divergence caused by making a major purchase today versus letting that capital compound.

---

### 6. Detailed Feature Specifications

#### 6.1 Data Ingestion & Local LLM Categorization Module
*   **Functional Requirements:**
    *   **Deterministic Caching Pipeline:** Upon reading a raw transaction string, the backend queries the `merchant_llm_cache` table.
        *   **Cache Hit:** If the string exists, apply the clean merchant name and category ID directly.
        *   **Cache Miss:** If the string is unmapped, trigger a local API request to the configured LLM endpoint using a structured system prompt. The model must return an isolated, valid JSON string containing `{"clean_merchant": "...", "category": "..."}`.
    *   **Persistence on Miss:** Write the returned data immediately to `merchant_llm_cache` to guarantee subsequent imports block redundant LLM generation cycles.
    *   **User Override Sync:** If a user modifies a category designation manually inside the React UI, the FastAPI backend updates the database cache record to mirror the choice for all past and future instances of that raw string.

#### 6.2 Sandbox Scenario "Compare Mode"
*   **Functional Requirements:**
    *   Provide single-click duplication of the core financial state container into an isolated sandbox branch.
    *   Allow asynchronous adjustments to the sandbox properties while maintaining a protected, un-mutated **Base Plan**.
    *   Deliver concurrent calculation data arrays back to the frontend presentation layer for delta graph mapping.

---

### 7. Technical Constraints & Data Lifecycle

*   **Discrete Time-Step Execution:** The simulation system computes calculations using a discrete monthly evaluation loop. For every increment index t representing a calendar month, net cash accounts update according to the formula:
    
    $$Cash\_Ending_t = Cash\_Starting_t + Inflows_t - Outflows_t - Milestone\_Costs_t$$

*   **Local Caching Processing Sequence:**
    1. User uploads a raw CSV bank file into the React container.
    2. React pipes rows to the local FastAPI parsing server.
    3. FastAPI initiates a step-through loop, querying SQLite table `merchant_llm_cache` using `raw_description`.
    4. On a *Cache Hit*, category IDs are applied instantly. On a *Cache Miss*, an asynchronous JSON block request fires to the local LLM endpoint (Ollama/Llama.cpp).
    5. The LLM response parses into SQLite, storing the mapping rule, and properties are written to the main `transactions` entity.
    6. Fresh JSON response arrays return to React, re-rendering UI charts instantly.

---

### 8. Open Source MVP Success Criteria
1.  **Air-Gapped Operational Stability:** The platform achieves 100% features capability—including structural spending categorization pipelines—on an un-networked computer hooked to an active local Ollama environment.
2.  **Dashboard Rendering Optimization:** Manual state transitions or slider modifications update both the 12-72 Month Cash Runway and 10-Year Macro Wealth charts within a maximum limit of 150ms.
3.  **Barrier-Free Core Ecosystem:** Financial simulations, sandbox environments, side-by-side strategy overlays, and categorization features remain entirely unrestricted by local license walls or premium tier locks.
