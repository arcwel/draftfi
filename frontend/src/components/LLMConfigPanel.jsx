import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store/useStore'
import { api } from '../lib/api'

const inputCls =
  'w-full rounded-md border border-edge bg-ink px-2 py-1 text-xs text-gray-100 focus:border-sky-500 focus:outline-none'

// LLM provider configuration + telemetry (PRD 4.1), extended to BYO cloud keys.
export default function LLMConfigPanel() {
  const llm = useStore((s) => s.llm)
  const config = useStore((s) => s.llmConfig)
  const saveLlmConfig = useStore((s) => s.saveLlmConfig)
  const deleteLlmKey = useStore((s) => s.deleteLlmKey)
  const saving = useStore((s) => s.savingLlmConfig)

  const [provider, setProvider] = useState('ollama')
  const [model, setModel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [keyInput, setKeyInput] = useState('')
  const [editingKey, setEditingKey] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)
  // A1 test-connection + A2 model-list local state.
  const [testResult, setTestResult] = useState(null) // {ok, latency_ms, detail}
  const [testing, setTesting] = useState(false)
  const [models, setModels] = useState([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [modelsError, setModelsError] = useState(null)
  // In-app dropdown (a native <datalist> popup renders outside the desktop
  // window in the packaged webview, so we draw the list ourselves).
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef(null)

  // Close the model dropdown when clicking anywhere outside it.
  useEffect(() => {
    if (!pickerOpen) return undefined
    const onPointerDown = (e) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) {
        setPickerOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [pickerOpen])

  const specs = config?.providers ?? []
  const active = specs.find((p) => p.id === provider)

  // Seed the form from stored config once it loads / when provider changes.
  useEffect(() => {
    if (!config) return
    setProvider(config.provider)
  }, [config])

  useEffect(() => {
    if (!config) return
    const spec = config.providers.find((p) => p.id === provider)
    if (!spec) return
    if (provider === config.provider) {
      setModel(config.model)
      setBaseUrl(config.base_url)
    } else {
      setModel(spec.default_model)
      setBaseUrl(spec.default_base_url)
    }
    setKeyInput('')
    setEditingKey(false)
    // Reset per-provider transient UI.
    setTestResult(null)
    setModels([])
    setModelsError(null)
    setPickerOpen(false)
  }, [provider, config])

  if (!config) {
    return <div className="text-xs text-gray-600">Loading LLM config…</div>
  }

  const needsKey = active?.requires_key
  const hasKey = active?.has_key
  const online = llm.available

  // Current (unsaved) form values for test / model-fetch.
  function draftConfig() {
    const c = { provider, model, base_url: baseUrl }
    if (keyInput.trim()) c.api_key = keyInput.trim()
    return c
  }

  async function onSave() {
    const payload = draftConfig()
    await saveLlmConfig(payload)
    setKeyInput('')
    setEditingKey(false)
    setSavedFlash(true)
    setTimeout(() => setSavedFlash(false), 1500)
  }

  async function onTest() {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await api.testLlm(draftConfig()))
    } catch (e) {
      setTestResult({ ok: false, detail: e.message })
    } finally {
      setTesting(false)
    }
  }

  async function onLoadModels() {
    setLoadingModels(true)
    setModelsError(null)
    try {
      const res = await api.llmModels(draftConfig())
      setModels(res.models)
      // Drop the list open right away so the models are visible in-app.
      setPickerOpen(res.models.length > 0)
      if (res.models.length === 0) setModelsError(res.detail || 'No models found')
    } catch (e) {
      setModelsError(e.message)
    } finally {
      setLoadingModels(false)
    }
  }

  return (
    <div className="space-y-2.5">
      {/* Telemetry pill */}
      <div className="rounded-lg border border-edge bg-panel px-3 py-2 text-xs">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-2 w-2 rounded-full ${online ? 'bg-emerald-400' : 'bg-rose-500'}`}
          />
          <span className="font-medium text-gray-200">
            {online ? 'Connected' : 'Not connected'}
          </span>
          {online && llm.latency_ms != null && (
            <span className="ml-auto text-gray-400">{llm.latency_ms} ms</span>
          )}
        </div>
        <div className="mt-1 truncate text-[11px] text-gray-500">
          {online ? `${llm.provider} · ${llm.model}` : llm.detail || 'not reachable'}
        </div>
        {!online && (
          <div className="mt-1 text-[11px] text-amber-400">
            New imports fall back to “Uncategorized”.
          </div>
        )}
      </div>

      {/* Provider selector */}
      <label className="block">
        <span className="text-[11px] text-gray-500">Provider</span>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className={inputCls}
        >
          {specs.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>

      {/* Model — free text plus an in-app dropdown of the provider's models. */}
      <div className="block">
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-gray-500">Model</span>
          <button
            type="button"
            onClick={onLoadModels}
            disabled={loadingModels}
            className="text-[10px] text-sky-300 hover:text-sky-200 disabled:opacity-50"
          >
            {loadingModels ? 'Loading…' : '↻ Load models'}
          </button>
        </div>

        <div className="relative" ref={pickerRef}>
          <input
            className={`${inputCls} ${models.length > 0 ? 'pr-7' : ''}`}
            value={model}
            placeholder={active?.model_hint}
            onChange={(e) => setModel(e.target.value)}
          />
          {models.length > 0 && (
            <button
              type="button"
              onClick={() => setPickerOpen((v) => !v)}
              title="Choose from available models"
              aria-label="Choose from available models"
              className="absolute inset-y-0 right-0 flex items-center px-2 text-xs text-gray-400 hover:text-sky-300"
            >
              {pickerOpen ? '▴' : '▾'}
            </button>
          )}

          {pickerOpen && models.length > 0 && (
            <ul className="absolute left-0 right-0 z-40 mt-1 max-h-48 overflow-y-auto rounded-md border border-edge bg-panel py-1 shadow-xl">
              {models.map((m) => (
                <li key={m}>
                  <button
                    type="button"
                    onClick={() => {
                      setModel(m)
                      setPickerOpen(false)
                    }}
                    className={`block w-full truncate px-2 py-1 text-left text-[11px] hover:bg-sky-950/60 ${
                      m === model ? 'text-sky-300' : 'text-gray-200'
                    }`}
                  >
                    {m}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {models.length > 0 && (
          <span className="mt-0.5 block text-[10px] text-gray-600">
            {models.length} models available — type or pick from the list
          </span>
        )}
        {modelsError && (
          <span className="mt-0.5 block text-[10px] text-amber-400">{modelsError}</span>
        )}
      </div>

      {/* Base URL — only meaningful for local providers */}
      {active?.is_local && (
        <label className="block">
          <span className="text-[11px] text-gray-500">Base URL</span>
          <input
            className={inputCls}
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </label>
      )}

      {/* API key */}
      {needsKey && (
        <div className="block">
          <span className="text-[11px] text-gray-500">API key</span>
          {hasKey && !editingKey ? (
            <div className="flex items-center gap-2">
              <span className="flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-xs text-gray-400">
                •••••••••••• stored
              </span>
              <button
                onClick={() => setEditingKey(true)}
                className="rounded-md border border-edge px-2 py-1 text-xs text-sky-300 hover:border-sky-500"
              >
                Update
              </button>
              <button
                onClick={() => deleteLlmKey(provider)}
                className="rounded-md border border-edge px-2 py-1 text-xs text-gray-500 hover:text-rose-400"
                title="Remove stored key"
              >
                ✕
              </button>
            </div>
          ) : (
            <input
              type="password"
              className={inputCls}
              value={keyInput}
              placeholder={hasKey ? 'Enter new key…' : 'Paste API key…'}
              onChange={(e) => setKeyInput(e.target.value)}
            />
          )}
          <p className="mt-1 text-[10px] text-gray-600">
            Stored locally in <code>sandbox.db</code>. Cloud providers send
            descriptor text to their API.
          </p>
        </div>
      )}

      {/* A1: test-connection result */}
      {testResult && (
        <div
          className={`rounded-md border px-2 py-1 text-[11px] ${
            testResult.ok
              ? 'border-emerald-800 bg-emerald-950/40 text-emerald-300'
              : 'border-rose-900 bg-rose-950/40 text-rose-300'
          }`}
        >
          {testResult.ok
            ? `✓ Connected${testResult.latency_ms != null ? ` · ${testResult.latency_ms} ms` : ''}`
            : `✕ ${testResult.detail || 'Connection failed'}`}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={onTest}
          disabled={testing}
          className="flex-1 rounded-md border border-edge py-1.5 text-xs font-medium text-gray-200 hover:border-sky-500 disabled:opacity-50"
        >
          {testing ? 'Testing…' : 'Test connection'}
        </button>
        <button
          onClick={onSave}
          disabled={saving}
          className="flex-1 rounded-md bg-sky-600 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {saving ? 'Saving…' : savedFlash ? 'Saved ✓' : 'Save configuration'}
        </button>
      </div>
    </div>
  )
}
