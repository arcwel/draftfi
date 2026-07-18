import { useEffect, useState } from 'react'
import { useStore } from '../store/useStore'

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
  }, [provider, config])

  if (!config) {
    return <div className="text-xs text-gray-600">Loading LLM config…</div>
  }

  const needsKey = active?.requires_key
  const hasKey = active?.has_key
  const online = llm.available

  async function onSave() {
    const payload = { provider, model, base_url: baseUrl }
    if (keyInput.trim()) payload.api_key = keyInput.trim()
    await saveLlmConfig(payload)
    setKeyInput('')
    setEditingKey(false)
    setSavedFlash(true)
    setTimeout(() => setSavedFlash(false), 1500)
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

      {/* Model */}
      <label className="block">
        <span className="text-[11px] text-gray-500">Model</span>
        <input
          className={inputCls}
          value={model}
          placeholder={active?.model_hint}
          onChange={(e) => setModel(e.target.value)}
        />
      </label>

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

      <button
        onClick={onSave}
        disabled={saving}
        className="w-full rounded-md bg-sky-600 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
      >
        {saving ? 'Saving…' : savedFlash ? 'Saved ✓' : 'Save configuration'}
      </button>
    </div>
  )
}
