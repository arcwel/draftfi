import { Component } from 'react'

// Catches render-time errors so one broken component can't white-screen the
// whole app; shows a recoverable fallback instead.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Surface to the console for debugging; no external reporting (local-first).
    console.error('DraftFi render error:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-ink px-4 text-center">
          <div className="max-w-sm rounded-2xl border border-edge bg-panel p-6">
            <h1 className="text-lg font-semibold text-white">Something went wrong</h1>
            <p className="mt-2 text-xs text-gray-500">
              A part of the app hit an unexpected error. Your data is safe on this
              machine.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
