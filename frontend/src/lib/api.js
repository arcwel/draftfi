// Thin API client for the FastAPI backend.
//
// In dev, calls go through the Vite `/api` proxy. In a production build (the
// packaged desktop app), the same FastAPI process serves this frontend, so we
// hit the API at the same origin with no prefix.
const BASE = import.meta.env.PROD ? '' : '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  llmStatus: () => request('/llm/status'),

  llmConfig: () => request('/llm/config'),

  saveLlmConfig: (config) =>
    request('/llm/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }),

  deleteLlmKey: (provider) =>
    request(`/llm/config/${provider}/key`, { method: 'DELETE' }),

  categories: () => request('/categories'),

  transactions: ({ limit = 50, offset = 0, q, sort_by, sort_dir } = {}) => {
    const params = new URLSearchParams({ limit, offset })
    if (q) params.set('q', q)
    if (sort_by) params.set('sort_by', sort_by)
    if (sort_dir) params.set('sort_dir', sort_dir)
    return request(`/transactions?${params}`)
  },

  splitTransaction: (txId, splits) =>
    request(`/transactions/${txId}/split`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ splits }),
    }),

  unsplitTransaction: (txId) =>
    request(`/transactions/${txId}/unsplit`, { method: 'POST' }),

  createCategory: (name, color) =>
    request('/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, color }),
    }),

  updateCategory: (id, patch) =>
    request(`/categories/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),

  deleteCategory: (id) => request(`/categories/${id}`, { method: 'DELETE' }),

  mergeCategory: (id, targetId) =>
    request(`/categories/${id}/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_id: targetId }),
    }),

  overrideCategory: (txId, categoryId) =>
    request(`/transactions/${txId}/category`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: categoryId }),
    }),

  createTransaction: (tx) =>
    request('/transactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tx),
    }),

  updateTransaction: (txId, patch) =>
    request(`/transactions/${txId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),

  deleteTransaction: (txId) =>
    request(`/transactions/${txId}`, { method: 'DELETE' }),

  parseScenario: (text) =>
    request('/scenario/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),

  // Download links (used as <a href>) and backup restore.
  exportUrl: (kind) => `${BASE}/export/${kind}`,

  restoreBackup: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/export/restore', { method: 'POST', body: form })
  },

  // Import one or more statement files (CSV/OFX/QFX/QIF). `mapping` supplies a
  // manual CSV column mapping when auto-detection failed.
  importFiles: (files, accountName, mapping) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    // A STABLE account label keeps re-imports idempotent (never the filename).
    form.append('account_name', (accountName || '').trim() || 'Imported Account')
    if (mapping) form.append('mapping', JSON.stringify(mapping))
    return request('/import/csv', { method: 'POST', body: form })
  },

  importStatus: (jobId) => request(`/import/status/${jobId}`),

  simulate: (parameters, milestones, events = []) =>
    request('/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parameters, milestones, events }),
    }),

  // E4: overlay Base + selected branches with a delta table.
  compareScenarios: (branchIds) =>
    request('/scenarios/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ branch_ids: branchIds }),
    }),

  // E5: goal CRUD.
  goals: () => request('/goals'),

  createGoal: (goal) =>
    request('/goals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(goal),
    }),

  updateGoal: (id, patch) =>
    request(`/goals/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),

  deleteGoal: (id) => request(`/goals/${id}`, { method: 'DELETE' }),

  budget: (parameters, milestones, month) =>
    request('/budget', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parameters, milestones, month: month ?? null }),
    }),

  trends: () => request('/budget/trends'),

  resetData: () => request('/reset', { method: 'POST' }),

  sync: () => request('/sync', { method: 'POST' }),

  syncStatus: (jobId) => request(`/sync/status/${jobId}`),

  setCategoryBudget: (categoryId, monthlyBudget, rollover) =>
    request(`/categories/${categoryId}/budget`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        monthly_budget: monthlyBudget,
        ...(rollover !== undefined ? { rollover } : {}),
      }),
    }),

  branches: () => request('/branches'),

  createBranch: (name, sourceBranchId = null) =>
    request('/branches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, source_branch_id: sourceBranchId }),
    }),

  updateBranch: (id, patch) =>
    request(`/branches/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),

  deleteBranch: (id) => request(`/branches/${id}`, { method: 'DELETE' }),

  compare: (branchId) => request(`/branches/${branchId}/compare`),
}
