import { useEffect } from 'react'
import { useShellStore, type Theme } from '@/store'

const STORAGE_KEY = 'agweb.theme'

export function loadInitialTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // storage unavailable — fall through to media query
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** Applies the theme to the DOM, persists it, and mirrors it to nativeTheme. */
export function useThemeEffect(): void {
  const theme = useShellStore((s) => s.theme)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // non-fatal
    }
    void window.agweb.setTheme(theme)
  }, [theme])
}
