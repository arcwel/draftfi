import { create } from 'zustand'
import { api } from '../lib/api'
import { setFormat } from '../lib/format'

const DEFAULT_PARAMS = {
  starting_cash: 25000,
  monthly_inflow: null, // null => backend derives from history
  monthly_outflow: null,
  income_adjustment_pct: 0,
  safety_floor: 5000,
  runway_months: 36,
  macro_years: 10,
  annual_return_pct: 6,
  annual_debt_rate_pct: 5,
  annual_inflation_pct: 0,
  starting_assets: 50000,
  starting_debt: 0,
}

// Central app state. Simulation is recomputed with a short debounce so slider
// drags stay within the 150ms end-to-end budget (Success Criterion 2).
export const useStore = create((set, get) => ({
  categories: [],
  transactions: [],
  totalTransactions: 0,

  llm: { available: false, latency_ms: null, provider: '', model: '', detail: null },
  llmConfig: null, // { provider, model, base_url, providers: [] }
  savingLlmConfig: false,

  branches: [],
  activeBranchId: null,
  overlay: false, // "Combined Overlay" compares active branch vs base

  parameters: { ...DEFAULT_PARAMS },
  milestones: [],
  events: [], // E2: income/expense change events for the active plan

  series: null, // single simulation result
  compare: null, // { base, branch } when overlay is on
  scenarioCompare: null, // E4: { scenarios, checkpoints, deltas }
  compareBranchIds: [], // E4: branches selected for multi-overlay
  goals: [], // E5: target net worth / cash records
  subscriptions: null, // A3: { items, total_monthly }
  insights: [], // A4: heuristic month-over-month insights
  updateInfo: null, // F1: { current, latest, update_available, url }
  updateDismissed: false, // F1: user closed the update banner this session
  preferences: { currency: 'USD', locale: 'en-US' }, // G4
  security: { passcode_set: false, locked: false }, // G2
  booted: false, // G2: security-gate check complete
  budget: null, // BudgetSummary: monthly spending + scenario impact
  trends: null, // TrendsSummary: month-over-month cash flow + category series
  budgetMonth: null, // null = all-time average; else "YYYY-MM"
  importing: false,
  importSummary: null,
  importProgress: null, // { processed, total } while an import runs
  // When a CSV can't be auto-mapped: { headers, sample_rows, signature, files }
  mappingNeeded: null,
  syncing: false,
  syncResult: null, // { recategorized, still_uncategorized, ... } shown briefly
  syncProgress: null, // { processed, total } while a sync runs

  // ---- bootstrapping ---- //
  // G2: run BEFORE loading data. Checks the passcode gate; only loads the app
  // (including preferences, which are gated while locked) once unlocked.
  async boot() {
    let security = { passcode_set: false, locked: false }
    try {
      const res = await api.security()
      // Guard against an unexpected/null shape so App never derefs undefined.
      if (res && typeof res.locked === 'boolean') security = res
    } catch {
      /* not reachable — treat as unlocked */
    }
    set({ security, booted: true })
    if (!security.locked) await get().init()
  },

  // G4: load and apply the saved currency/locale (runs post-unlock via init).
  async loadPreferences() {
    try {
      const prefs = await api.preferences()
      if (prefs && prefs.currency && prefs.locale) {
        setFormat(prefs)
        set({ preferences: prefs })
      }
    } catch {
      /* keep defaults */
    }
  },

  async unlock(passcode) {
    let res
    try {
      res = await api.unlock(passcode)
    } catch {
      return false // offline / server error — LockScreen shows a retry
    }
    if (res.ok) {
      set({ security: { ...get().security, locked: false } })
      await get().init()
    }
    return res.ok
  },

  // G4: change currency/locale. Updating `preferences` re-keys the workspace in
  // App, remounting it so every formatted value re-renders in the new currency.
  async updatePreferences(patch) {
    const prefs = await api.setPreferences(patch)
    setFormat(prefs)
    set({ preferences: prefs })
  },

  // G2: passcode management (from the settings panel).
  async setPasscode(passcode, current) {
    const security = await api.setPasscode(passcode, current)
    set({ security })
  },

  async removePasscode(current) {
    const security = await api.clearPasscode(current)
    set({ security })
  },

  async init() {
    // allSettled so one failing endpoint (500/offline) can't abort the rest or
    // skip recompute — the app still renders what loaded and stays interactive.
    await Promise.allSettled([
      get().loadCategories(),
      get().loadTransactions(),
      get().loadBranches(),
      get().pollLlm(),
      get().loadLlmConfig(),
      get().loadGoals(),
      get().checkForUpdate(),
      get().loadPreferences(),
    ])
    await get().recompute()
  },

  // F1: fetch the latest release info once at launch (fails silently offline).
  async checkForUpdate() {
    try {
      set({ updateInfo: await api.updateCheck() })
    } catch {
      /* offline / not packaged — no banner */
    }
  },

  dismissUpdate() {
    set({ updateDismissed: true })
  },

  async loadLlmConfig() {
    try {
      set({ llmConfig: await api.llmConfig() })
    } catch {
      /* backend not ready yet */
    }
  },

  async saveLlmConfig(config) {
    set({ savingLlmConfig: true })
    try {
      const updated = await api.saveLlmConfig(config)
      set({ llmConfig: updated })
      await get().pollLlm()
    } finally {
      set({ savingLlmConfig: false })
    }
  },

  async deleteLlmKey(provider) {
    const updated = await api.deleteLlmKey(provider)
    set({ llmConfig: updated })
    await get().pollLlm()
  },

  async loadCategories() {
    set({ categories: await api.categories() })
  },

  // Ledger query state — search/sort/paging run server-side over the full DB.
  txQuery: '',
  txSort: { by: 'date', dir: 'desc' },
  txPage: 0,
  txPageSize: 50,

  async loadTransactions() {
    const { txQuery, txSort, txPage, txPageSize } = get()
    const page = await api.transactions({
      limit: txPageSize,
      offset: txPage * txPageSize,
      q: txQuery || undefined,
      sort_by: txSort.by,
      sort_dir: txSort.dir,
    })
    set({ transactions: page.items, totalTransactions: page.total })
  },

  setTxQuery(q) {
    set({ txQuery: q, txPage: 0 })
    get().loadTransactions()
  },

  setTxSort(by) {
    const cur = get().txSort
    const dir = cur.by === by && cur.dir === 'desc' ? 'asc' : 'desc'
    set({ txSort: { by, dir }, txPage: 0 })
    get().loadTransactions()
  },

  setTxPage(page) {
    set({ txPage: Math.max(0, page) })
    get().loadTransactions()
  },

  async pollLlm() {
    try {
      set({ llm: await api.llmStatus() })
    } catch {
      set({ llm: { available: false, latency_ms: null, model: '', detail: 'offline' } })
    }
  },

  async loadBranches() {
    const branches = await api.branches()
    const base = branches.find((b) => b.is_base)
    const current = get().activeBranchId
    set({
      branches,
      activeBranchId: current ?? base?.id ?? null,
    })
    // Adopt the active branch's parameters into the editable strip.
    const active = branches.find((b) => b.id === (current ?? base?.id))
    if (active) {
      set({
        parameters: { ...DEFAULT_PARAMS, ...active.parameters },
        milestones: active.milestones,
        events: active.events || [],
      })
    }
  },

  setActiveBranch(id) {
    const branch = get().branches.find((b) => b.id === id)
    set({
      activeBranchId: id,
      parameters: branch ? { ...DEFAULT_PARAMS, ...branch.parameters } : get().parameters,
      milestones: branch ? branch.milestones : get().milestones,
      events: branch ? branch.events || [] : get().events,
    })
    get().recompute()
  },

  toggleOverlay() {
    set({ overlay: !get().overlay })
    get().recompute()
  },

  // ---- parameter editing ---- //
  setParam(key, value) {
    set({ parameters: { ...get().parameters, [key]: value } })
    get().debouncedRecompute()
    get().persistActiveBranch()
  },

  addMilestone(m) {
    set({ milestones: [...get().milestones, m] })
    get().recompute()
    get().persistActiveBranch()
  },

  updateMilestone(index, m) {
    const next = get().milestones.slice()
    next[index] = m
    set({ milestones: next })
    get().recompute()
    get().persistActiveBranch()
  },

  removeMilestone(index) {
    set({ milestones: get().milestones.filter((_, i) => i !== index) })
    get().recompute()
    get().persistActiveBranch()
  },

  // 'idle' | 'saving' | 'saved' — surfaced in the branch manager.
  branchSaveState: 'idle',

  // Persist edits to the active plan. The Base Plan is editable too — it holds
  // your real baseline (income, spending, assets); only deletion is blocked.
  async persistActiveBranch() {
    const { activeBranchId, branches, parameters, milestones, events } = get()
    const active = branches.find((b) => b.id === activeBranchId)
    if (!active) {
      set({ branchSaveState: 'idle' })
      return
    }
    set({ branchSaveState: 'saving' })
    try {
      await api.updateBranch(activeBranchId, { parameters, milestones, events })
      // Keep the in-memory branch in sync so switching away and back is correct.
      set({
        branchSaveState: 'saved',
        branches: get().branches.map((b) =>
          b.id === activeBranchId ? { ...b, parameters, milestones, events } : b,
        ),
      })
    } catch {
      set({ branchSaveState: 'idle' }) // non-fatal: keep local edits
    }
  },

  // ---- E2: income/expense change events (mirror milestone handling) ---- //
  addEvent(ev) {
    set({ events: [...get().events, ev] })
    get().recompute()
    get().persistActiveBranch()
  },

  updateEvent(index, ev) {
    const next = get().events.slice()
    next[index] = ev
    set({ events: next })
    get().recompute()
    get().persistActiveBranch()
  },

  removeEvent(index) {
    set({ events: get().events.filter((_, i) => i !== index) })
    get().recompute()
    get().persistActiveBranch()
  },

  // ---- branch management ---- //
  async createBranch(name) {
    const source = get().activeBranchId
    const branch = await api.createBranch(name, source)
    await get().loadBranches()
    get().setActiveBranch(branch.id)
  },

  async deleteBranch(id) {
    await api.deleteBranch(id)
    const base = get().branches.find((b) => b.is_base)
    set({
      activeBranchId: base?.id ?? null,
      compareBranchIds: get().compareBranchIds.filter((x) => x !== id),
    })
    await get().loadBranches()
    get().recompute()
  },

  // Rename a sandbox branch (Base Plan name is fixed). Persists to the DB.
  async renameBranch(id, name) {
    const trimmed = (name || '').trim()
    if (!trimmed) return
    const updated = await api.updateBranch(id, { name: trimmed })
    set({
      branches: get().branches.map((b) => (b.id === id ? { ...b, name: updated.name } : b)),
    })
  },

  // ---- simulation ---- //
  _timer: null,
  debouncedRecompute() {
    if (get()._timer) clearTimeout(get()._timer)
    const t = setTimeout(() => get().recompute(), 120)
    set({ _timer: t })
  },

  async recompute() {
    const { parameters, milestones, events, overlay, activeBranchId, branches } = get()
    const active = branches.find((b) => b.id === activeBranchId)
    // allSettled + a guarded forecast branch so a failed simulate/compare (fired
    // and forgotten from slider drags) can't become an unhandled rejection.
    await Promise.allSettled([
      (async () => {
        try {
          if (overlay && active && !active.is_base) {
            const cmp = await api.compare(activeBranchId)
            set({ compare: cmp, series: cmp.branch })
          } else {
            const series = await api.simulate(parameters, milestones, events)
            set({ series, compare: null })
          }
        } catch {
          /* keep the last good forecast */
        }
      })(),
      get().loadBudget(),
      get().loadScenarioCompare(),
      get().loadAnalytics(),
    ])
  },

  // A3/A4: recurring charges + insights derive from the transaction history.
  async loadAnalytics() {
    try {
      const [subscriptions, insights] = await Promise.all([
        api.subscriptions(),
        api.insights(),
      ])
      set({ subscriptions, insights: insights.insights })
    } catch {
      /* non-fatal */
    }
  },

  // ---- E4: multi-branch compare ---- //
  toggleCompareBranch(id) {
    const cur = get().compareBranchIds
    const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]
    set({ compareBranchIds: next })
    get().loadScenarioCompare()
  },

  async loadScenarioCompare() {
    const ids = get().compareBranchIds
    if (ids.length === 0) {
      set({ scenarioCompare: null })
      return
    }
    try {
      set({ scenarioCompare: await api.compareScenarios(ids) })
    } catch {
      /* non-fatal */
    }
  },

  // ---- E5: goals ---- //
  async loadGoals() {
    try {
      set({ goals: await api.goals() })
    } catch {
      /* backend not ready */
    }
  },

  async createGoal(goal) {
    await api.createGoal(goal)
    await get().loadGoals()
  },

  async updateGoal(id, patch) {
    await api.updateGoal(id, patch)
    await get().loadGoals()
  },

  async deleteGoal(id) {
    await api.deleteGoal(id)
    await get().loadGoals()
  },

  async loadBudget() {
    const { parameters, milestones, budgetMonth } = get()
    try {
      const [budget, trends] = await Promise.all([
        api.budget(parameters, milestones, budgetMonth),
        api.trends(),
      ])
      set({ budget, trends })
    } catch {
      /* non-fatal */
    }
  },

  setBudgetMonth(month) {
    set({ budgetMonth: month })
    get().loadBudget()
  },

  async setCategoryBudget(categoryId, monthlyBudget, rollover) {
    await api.setCategoryBudget(categoryId, monthlyBudget, rollover)
    await Promise.all([get().loadCategories(), get().loadBudget()])
  },

  // ---- import (CSV/OFX/QFX/QIF, one or many files) ---- //
  async importFiles(files, accountName, mapping = null) {
    const fileList = Array.from(files)
    set({
      importing: true,
      importSummary: null,
      importProgress: { processed: 0, total: 0 },
    })
    try {
      const { job_id } = await api.importFiles(fileList, accountName, mapping)
      const final = await get()._pollJob(api.importStatus, job_id, (s) =>
        set({ importProgress: { processed: s.processed, total: s.total } }),
      )
      if (final && final.state === 'needs_mapping') {
        // Hold the files so the mapping dialog can re-submit them.
        set({
          mappingNeeded: {
            headers: final.headers,
            sample_rows: final.sample_rows,
            signature: final.signature,
            files: fileList,
            account: accountName,
          },
        })
        return final
      }
      set({ importSummary: final, mappingNeeded: null })
      await Promise.all([get().loadTransactions(), get().pollLlm()])
      await get().recompute()
      return final
    } finally {
      set({ importing: false, importProgress: null })
    }
  },

  // Re-run an import that stalled on mapping, now with the user's column map.
  async submitMapping(mapping) {
    const pending = get().mappingNeeded
    if (!pending) return
    set({ mappingNeeded: null })
    await get().importFiles(pending.files, pending.account, mapping)
  },

  cancelMapping() {
    set({ mappingNeeded: null })
  },

  async overrideCategory(txId, categoryId) {
    await api.overrideCategory(txId, categoryId)
    await get().loadTransactions()
    await get().recompute()
  },

  // ---- manual transaction CRUD ---- //
  async createTransaction(tx) {
    await api.createTransaction(tx)
    await get().loadTransactions()
    await get().recompute()
  },

  async updateTransaction(txId, patch) {
    await api.updateTransaction(txId, patch)
    await get().loadTransactions()
    await get().recompute()
  },

  async deleteTransaction(txId) {
    await api.deleteTransaction(txId)
    await get().loadTransactions()
    await get().recompute()
  },

  async splitTransaction(txId, splits) {
    await api.splitTransaction(txId, splits)
    await get().loadTransactions()
    await get().recompute()
  },

  async unsplitTransaction(txId) {
    await api.unsplitTransaction(txId)
    await get().loadTransactions()
    await get().recompute()
  },

  // ---- category management ---- //
  async createCategory(name, color) {
    await api.createCategory(name, color)
    await Promise.all([get().loadCategories(), get().loadBudget()])
  },

  async updateCategory(id, patch) {
    await api.updateCategory(id, patch)
    await Promise.all([get().loadCategories(), get().loadTransactions()])
    await get().loadBudget()
  },

  async deleteCategory(id) {
    await api.deleteCategory(id)
    await Promise.all([get().loadCategories(), get().loadTransactions()])
    await get().recompute()
  },

  async mergeCategory(id, targetId) {
    await api.mergeCategory(id, targetId)
    await Promise.all([get().loadCategories(), get().loadTransactions()])
    await get().recompute()
  },

  // ---- natural-language scenario ---- //
  scenarioParsing: false,
  scenarioNote: null,

  async applyScenarioText(text) {
    set({ scenarioParsing: true, scenarioNote: null })
    try {
      const result = await api.parseScenario(text)
      // Merge parsed inputs into the active plan.
      const params = { ...get().parameters, ...result.parameters }
      const milestones = [...get().milestones, ...result.milestones]
      set({ parameters: params, milestones })
      await get().persistActiveBranch()
      await get().recompute()
      const note =
        result.note ||
        (result.milestones.length
          ? `Added ${result.milestones.length} milestone(s).`
          : 'No changes detected in that description.')
      set({ scenarioNote: note })
      setTimeout(() => {
        if (get().scenarioNote === note) set({ scenarioNote: null })
      }, 10000)
      return result
    } finally {
      set({ scenarioParsing: false })
    }
  },

  // Poll a background job's status endpoint until it reaches a terminal state,
  // reporting progress via onProgress. Returns the final status object.
  async _pollJob(statusFn, jobId, onProgress) {
    const TERMINAL = new Set(['done', 'error', 'needs_mapping'])
    // eslint-disable-next-line no-constant-condition
    while (true) {
      let status
      try {
        status = await statusFn(jobId)
      } catch {
        return null
      }
      onProgress(status)
      if (TERMINAL.has(status.state)) return status
      await new Promise((r) => setTimeout(r, 400))
    }
  },

  // Process new information: re-categorize unresolved rows + refresh everything.
  async sync() {
    if (get().syncing) return
    set({ syncing: true, syncProgress: { processed: 0, total: 0 } })
    try {
      const { job_id } = await api.sync()
      const final = await get()._pollJob(api.syncStatus, job_id, (s) =>
        set({ syncProgress: { processed: s.processed, total: s.total } }),
      )
      await Promise.all([
        get().pollLlm(),
        get().loadCategories(),
        get().loadTransactions(),
        get().loadBranches(),
      ])
      await get().recompute()
      set({ syncResult: final })
      setTimeout(() => {
        if (get().syncResult === final) set({ syncResult: null })
      }, 6000)
    } finally {
      set({ syncing: false, syncProgress: null })
    }
  },

  // Wipe all financial data back to an empty slate (keeps categories + LLM keys).
  async resetAll() {
    await api.resetData()
    const base = await api.branches()
    const baseId = base.find((b) => b.is_base)?.id ?? null
    set({
      activeBranchId: baseId,
      overlay: false,
      importSummary: null,
      compareBranchIds: [],
      scenarioCompare: null,
    })
    await Promise.all([get().loadBranches(), get().loadTransactions()])
    await get().recompute()
  },
}))
