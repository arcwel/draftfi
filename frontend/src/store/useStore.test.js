import { beforeEach, describe, expect, it, vi } from 'vitest'

// Mock the API client so the store never touches the network.
vi.mock('../lib/api', () => ({
  api: {
    preferences: vi.fn().mockResolvedValue({ currency: 'USD', locale: 'en-US' }),
    security: vi.fn(),
    categories: vi.fn().mockResolvedValue([]),
  },
}))

import { api } from '../lib/api'
import { useStore } from './useStore'

describe('store boot gate (G2)', () => {
  beforeEach(() => {
    useStore.setState({
      booted: false,
      security: { passcode_set: false, locked: false },
      categories: [],
    })
    vi.clearAllMocks()
  })

  it('does NOT load data while locked', async () => {
    api.security.mockResolvedValue({ passcode_set: true, locked: true })
    await useStore.getState().boot()

    const s = useStore.getState()
    expect(s.booted).toBe(true)
    expect(s.security.locked).toBe(true)
    // init() must not have run — no data fetched behind the lock.
    expect(api.categories).not.toHaveBeenCalled()
  })

  it('dismissUpdate hides the update banner', () => {
    useStore.setState({ updateDismissed: false })
    useStore.getState().dismissUpdate()
    expect(useStore.getState().updateDismissed).toBe(true)
  })
})
