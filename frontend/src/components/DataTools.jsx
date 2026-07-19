import { useRef, useState } from 'react'
import { api } from '../lib/api'

const linkCls =
  'block w-full rounded-md border border-edge bg-panel px-2.5 py-1.5 text-center text-xs text-gray-300 hover:border-sky-500 hover:text-sky-300'

// Data portability: exports, full backup, and restore. Local-first means the
// user can always get their data out.
export default function DataTools() {
  const fileRef = useRef(null)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)

  async function handleRestore(file) {
    if (!file) return
    setError(null)
    setStatus(null)
    const ok = window.confirm(
      'Restore this backup?\n\nYour current data will be replaced by the ' +
        'backup (a copy of the current database is kept next to it). The app ' +
        'will reload afterwards.',
    )
    if (!ok) return
    try {
      const result = await api.restoreBackup(file)
      setStatus(`Restored ${result.transactions} transactions. Reloading…`)
      setTimeout(() => window.location.reload(), 900)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="space-y-1.5">
      <a href={api.exportUrl('transactions.csv')} download className={linkCls}>
        Export transactions (CSV)
      </a>
      <a href={api.exportUrl('data.json')} download className={linkCls}>
        Export everything (JSON)
      </a>
      <a href={api.exportUrl('backup.db')} download className={linkCls}>
        Download backup
      </a>
      <button onClick={() => fileRef.current?.click()} className={linkCls}>
        Restore from backup…
      </button>
      <input
        ref={fileRef}
        type="file"
        accept=".db"
        className="hidden"
        onChange={(e) => handleRestore(e.target.files?.[0])}
      />
      {status && <p className="text-[11px] text-emerald-400">{status}</p>}
      {error && <p className="text-[11px] text-rose-400">{error}</p>}
    </div>
  )
}
