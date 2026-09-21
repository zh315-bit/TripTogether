import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

describe('Application', () => {
  it('renders the public landing page', () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Plan together.Travel better.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start planning' })).toBeInTheDocument()
  })

  it('shows Not Found and navigates home without a full reload', async () => {
    window.history.replaceState(null, '', '/missing')
    vi.stubGlobal('fetch', vi.fn())
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: 'Return home' }))
    expect(await screen.findByRole('heading', { name: 'Plan together.Travel better.' })).toBeInTheDocument()
  })
})
