import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const failure = (status: number, code: string, message: string) => json({ error: { code, message, details: [] } }, status)

function mount(path: string) {
  window.history.replaceState(null, '', path)
  render(<App />)
}

describe('password reset pages', () => {
  it('asks for a reset link without revealing whether the address exists', async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ status: 'accepted' }, 202))
    vi.stubGlobal('fetch', fetcher)
    mount('/login')
    await userEvent.click(await screen.findByRole('link', { name: 'Forgot password?' }))
    await userEvent.type(screen.getByLabelText('Email'), 'reader@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('status')).toHaveTextContent(/If an account exists for that address/)
    const call = fetcher.mock.calls.find(([url]) => String(url).endsWith('/auth/password/forgot'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ email: 'reader@example.com' })
  })

  it('explains when the server cannot send mail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failure(503, 'PASSWORD_RESET_UNAVAILABLE', 'Password reset is not available on this server')))
    mount('/forgot-password')
    await userEvent.type(await screen.findByLabelText('Email'), 'reader@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('not available on this server')
  })

  it('sets a new password from the mailed link and handles a spent link', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    mount('/reset-password?token=tok-123')
    await userEvent.type(await screen.findByLabelText('New password'), 'a-brand-new-password')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'different')
    await userEvent.click(screen.getByRole('button', { name: 'Set new password' }))
    expect(screen.getByRole('alert')).toHaveTextContent('do not match')
    expect(fetcher.mock.calls.some(([url]) => String(url).endsWith('/password/reset'))).toBe(false)
    await userEvent.clear(screen.getByLabelText('Confirm new password'))
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'a-brand-new-password')
    await userEvent.click(screen.getByRole('button', { name: 'Set new password' }))
    expect(await screen.findByRole('status')).toHaveTextContent('password has been changed')
    const call = fetcher.mock.calls.find(([url]) => String(url).endsWith('/password/reset'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ token: 'tok-123', password: 'a-brand-new-password' })
    const card = screen.getByRole('region', { name: 'Choose a new password' })
    expect(within(card).getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login')

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failure(400, 'INVALID_RESET_TOKEN', 'This reset link is invalid, used or expired')))
    mount('/reset-password?token=spent')
    const forms = await screen.findAllByLabelText('New password')
    await userEvent.type(forms[forms.length - 1], 'a-brand-new-password')
    const confirms = screen.getAllByLabelText('Confirm new password')
    await userEvent.type(confirms[confirms.length - 1], 'a-brand-new-password')
    const buttons = screen.getAllByRole('button', { name: 'Set new password' })
    await userEvent.click(buttons[buttons.length - 1])
    expect(await screen.findByRole('alert')).toHaveTextContent('Request a new one')
  })

  it('refuses a link without a token', async () => {
    mount('/reset-password')
    expect(await screen.findByRole('alert')).toHaveTextContent('missing its token')
  })
})
