import { create } from 'zustand'
import { api } from '../lib/api'

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

  series: null, // single simulation result
  compare: null, // { base, branch } when overlay is on
  budget: null, // BudgetSummary: monthly spending + scenario impact
  importing: false,
  importSummary: null,

  // ---- bootstrapping ---- //
  async init() {
    await Promise.all([
      get().loadCategories(),
      get().loadTransactions(),
      get().loadBranches(),
      get().pollLlm(),
      get().loadLlmConfig(),
    ])
    await get().recompute()
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

  async loadTransactions() {
    const page = await api.transactions(500, 0)
    set({ transactions: page.items, totalTransactions: page.total })
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
      set({ parameters: { ...DEFAULT_PARAMS, ...active.parameters }, milestones: active.milestones })
    }
  },

  setActiveBranch(id) {
    const branch = get().branches.find((b) => b.id === id)
    set({
      activeBranchId: id,
      parameters: branch ? { ...DEFAULT_PARAMS, ...branch.parameters } : get().parameters,
      milestones: branch ? branch.milestones : get().milestones,
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

  // Persist edits to the active branch (base is immutable — skip it).
  async persistActiveBranch() {
    const { activeBranchId, branches, parameters, milestones } = get()
    const active = branches.find((b) => b.id === activeBranchId)
    if (!active || active.is_base) {
      set({ branchSaveState: 'idle' })
      return
    }
    set({ branchSaveState: 'saving' })
    try {
      await api.updateBranch(activeBranchId, { parameters, milestones })
      // Keep the in-memory branch in sync so switching away and back is correct.
      set({
        branchSaveState: 'saved',
        branches: get().branches.map((b) =>
          b.id === activeBranchId ? { ...b, parameters, milestones } : b,
        ),
      })
    } catch {
      set({ branchSaveState: 'idle' }) // non-fatal: keep local edits
    }
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
    set({ activeBranchId: base?.id ?? null })
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
    const { parameters, milestones, overlay, activeBranchId, branches } = get()
    const active = branches.find((b) => b.id === activeBranchId)
    // Forecast (runway + macro) and budget update together off the same inputs.
    await Promise.all([
      (async () => {
        if (overlay && active && !active.is_base) {
          const cmp = await api.compare(activeBranchId)
          set({ compare: cmp, series: cmp.branch })
        } else {
          const series = await api.simulate(parameters, milestones)
          set({ series, compare: null })
        }
      })(),
      get().loadBudget(),
    ])
  },

  async loadBudget() {
    const { parameters, milestones } = get()
    try {
      set({ budget: await api.budget(parameters, milestones) })
    } catch {
      /* non-fatal */
    }
  },

  async setCategoryBudget(categoryId, monthlyBudget) {
    await api.setCategoryBudget(categoryId, monthlyBudget)
    await Promise.all([get().loadCategories(), get().loadBudget()])
  },

  // ---- import ---- //
  async importCsv(file, accountName) {
    set({ importing: true, importSummary: null })
    try {
      const summary = await api.importCsv(file, accountName)
      set({ importSummary: summary })
      await Promise.all([get().loadTransactions(), get().pollLlm()])
      await get().recompute()
    } finally {
      set({ importing: false })
    }
  },

  async overrideCategory(txId, categoryId) {
    await api.overrideCategory(txId, categoryId)
    await get().loadTransactions()
    await get().recompute()
  },
}))
