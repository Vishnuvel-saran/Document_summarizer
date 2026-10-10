import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('App', () => {
  it('displays the backend service status when the health check succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', service: 'document-intelligence-api' }),
      }),
    )

    render(<App />)

    expect(await screen.findByText(/document intelligence api/i)).toBeInTheDocument()
    expect(screen.getByText(/status: ok/i)).toBeInTheDocument()
  })

  it('shows an unavailable state when the backend request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network Error')))

    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText(/backend unavailable/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /retry/i }))
    expect(screen.getByText(/retrying/i)).toBeInTheDocument()
  })
})
