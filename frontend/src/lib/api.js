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
  health: () => request('/health'),
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

  transactions: (limit = 200, offset = 0) =>
    request(`/transactions?limit=${limit}&offset=${offset}`),

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

  importCsv: (file, accountName) => {
    const form = new FormData()
    form.append('file', file)
    // A STABLE account label keeps re-imports idempotent. We deliberately do
    // NOT use the filename (which changes between downloads). The CSV's own
    // account column, when present, still takes precedence on the backend.
    form.append('account_name', (accountName || '').trim() || 'Imported Account')
    return request('/import/csv', { method: 'POST', body: form })
  },

  importStatus: (jobId) => request(`/import/status/${jobId}`),

  simulate: (parameters, milestones) =>
    request('/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parameters, milestones }),
    }),

  budget: (parameters, milestones) =>
    request('/budget', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parameters, milestones }),
    }),

  resetData: () => request('/reset', { method: 'POST' }),

  sync: () => request('/sync', { method: 'POST' }),

  syncStatus: (jobId) => request(`/sync/status/${jobId}`),

  setCategoryBudget: (categoryId, monthlyBudget) =>
    request(`/categories/${categoryId}/budget`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ monthly_budget: monthlyBudget }),
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
