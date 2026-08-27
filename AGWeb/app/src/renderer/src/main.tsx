import React from 'react'
import ReactDOM from 'react-dom/client'
import App from '@/App'
import { useShellStore } from '@/store'
import { loadInitialTheme } from '@/theme'
import { installShortcutListener } from '@/shortcuts'
import '@/styles.css'

useShellStore.setState({ theme: loadInitialTheme() })
installShortcutListener()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
