import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { useStore } from '../store/useStore'
import LockScreen from './LockScreen'

describe('LockScreen (G2)', () => {
  it('submits the entered passcode to unlock', async () => {
    const unlock = vi.fn().mockResolvedValue(true)
    useStore.setState({ unlock })

    render(<LockScreen />)
    await userEvent.type(screen.getByPlaceholderText('Passcode'), '1234')
    await userEvent.click(screen.getByRole('button', { name: /unlock/i }))

    expect(unlock).toHaveBeenCalledWith('1234')
  })

  it('shows an error when the passcode is wrong', async () => {
    useStore.setState({ unlock: vi.fn().mockResolvedValue(false) })

    render(<LockScreen />)
    await userEvent.type(screen.getByPlaceholderText('Passcode'), '0000')
    await userEvent.click(screen.getByRole('button', { name: /unlock/i }))

    expect(await screen.findByText(/incorrect passcode/i)).toBeInTheDocument()
  })
})
