import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { useShellStore } from '@/store'

/**
 * xterm.js frontend for a main-process pty session keyed by the block id.
 * The session outlives this component: hiding the deck or moving the block
 * just re-attaches, replaying buffered scrollback.
 */

const DARK = { background: '#0e1420', foreground: '#e2e8f0', cursor: '#7dd3fc' }
const LIGHT = { background: '#ffffff', foreground: '#0f172a', cursor: '#0284c7' }

export function TerminalBlock({ id }: { id: string }): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const theme = useShellStore((s) => s.theme)
  const termRef = useRef<Terminal | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const term = new Terminal({
      fontSize: 12,
      fontFamily: "ui-monospace, 'SF Mono', Menlo, monospace",
      theme: useShellStore.getState().theme === 'dark' ? DARK : LIGHT,
      cursorBlink: true
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(container)
    fit.fit()
    termRef.current = term

    // Data events that arrive before the attach reply are already contained
    // in the snapshot buffer (main appends before broadcasting), so writing
    // them live AND replaying the buffer would duplicate scrollback. Hold
    // live writes until the snapshot lands, then drop the overlap.
    let attached = false
    void window.agweb.terminal.attach(id).then(({ buffer, running }) => {
      if (buffer) term.write(buffer)
      attached = true
      if (!running) void window.agweb.terminal.create(id, term.cols, term.rows)
      else void window.agweb.terminal.resize(id, term.cols, term.rows)
    })

    const offInput = term.onData((data) => void window.agweb.terminal.input(id, data))
    const offData = window.agweb.terminal.onData((termId, data) => {
      if (termId === id && attached) term.write(data)
    })
    const offExit = window.agweb.terminal.onExit((termId, code) => {
      if (termId === id) term.write(`\r\n[process exited with code ${code}]\r\n`)
    })

    const observer = new ResizeObserver(() => {
      fit.fit()
      void window.agweb.terminal.resize(id, term.cols, term.rows)
    })
    observer.observe(container)

    return () => {
      observer.disconnect()
      offInput.dispose()
      offData()
      offExit()
      termRef.current = null
      term.dispose()
    }
  }, [id])

  useEffect(() => {
    if (termRef.current) termRef.current.options.theme = theme === 'dark' ? DARK : LIGHT
  }, [theme])

  return <div ref={containerRef} className="h-full w-full bg-white pl-2 pt-1 dark:bg-[#0e1420]" />
}
