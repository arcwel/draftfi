import { useEffect, useState } from 'react'
import type { AppInfo } from '@shared/ipc'
import { useShellStore } from '@/store'

export function StatusBar(): React.JSX.Element {
  const workspace = useShellStore((s) => s.workspace)
  const theme = useShellStore((s) => s.theme)
  const setTheme = useShellStore((s) => s.setTheme)
  const [info, setInfo] = useState<AppInfo | null>(null)

  useEffect(() => {
    void window.agweb.getAppInfo().then(setInfo)
  }, [])

  return (
    <footer className="flex h-6 shrink-0 items-center gap-4 border-t border-slate-200 bg-slate-100 px-3 text-xs text-slate-500 dark:border-slate-800 dark:bg-[#0e1420]">
      <span>{workspace ? workspace.name : 'No project open'}</span>
      <span className="ml-auto">
        {info ? `AGWeb ${info.version} · Electron ${info.electron} · Chromium ${info.chrome}` : ''}
      </span>
      <button
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        className="hover:text-slate-700 dark:hover:text-slate-300"
        title="Toggle theme (mod+shift+L)"
      >
        {theme === 'dark' ? '☾ Dark' : '☀ Light'}
      </button>
    </footer>
  )
}
