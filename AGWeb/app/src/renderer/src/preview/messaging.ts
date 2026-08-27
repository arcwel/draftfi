/**
 * Cross-window messaging for embedded previews (PRD: Postmate/PostMessage).
 *
 * A Postmate-style handshake over the raw postMessage API: the host creates a
 * PreviewChannel around an iframe, the guest page answers the handshake, and
 * both sides then exchange { source, type, payload } envelopes. Origins are
 * pinned at construction — messages from any other origin are dropped.
 */

const PROTOCOL = 'agweb-preview/1'

export interface PreviewMessage<T = unknown> {
  source: typeof PROTOCOL
  type: string
  payload: T
}

type Listener = (payload: unknown) => void

export class PreviewChannel {
  private readonly listeners = new Map<string, Set<Listener>>()
  private readonly onMessage = (event: MessageEvent): void => {
    if (event.origin !== this.origin) return
    const data = event.data as Partial<PreviewMessage>
    if (data?.source !== PROTOCOL || typeof data.type !== 'string') return
    this.listeners.get(data.type)?.forEach((listener) => listener(data.payload))
  }

  constructor(
    private readonly frame: HTMLIFrameElement,
    private readonly origin: string
  ) {
    window.addEventListener('message', this.onMessage)
  }

  /** Ping the guest until it acks, or give up after `timeoutMs`. */
  async handshake(timeoutMs = 5000): Promise<boolean> {
    return new Promise((resolve) => {
      const started = performance.now()
      const stop = this.on('handshake-ack', () => {
        clearInterval(timer)
        stop()
        resolve(true)
      })
      const timer = setInterval(() => {
        if (performance.now() - started > timeoutMs) {
          clearInterval(timer)
          stop()
          resolve(false)
          return
        }
        this.send('handshake', null)
      }, 100)
    })
  }

  send<T>(type: string, payload: T): void {
    const message: PreviewMessage<T> = { source: PROTOCOL, type, payload }
    this.frame.contentWindow?.postMessage(message, this.origin)
  }

  on(type: string, listener: Listener): () => void {
    const set = this.listeners.get(type) ?? new Set()
    set.add(listener)
    this.listeners.set(type, set)
    return () => set.delete(listener)
  }

  destroy(): void {
    window.removeEventListener('message', this.onMessage)
    this.listeners.clear()
  }
}
