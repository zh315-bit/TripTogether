/// <reference types="node" />
import process from 'node:process'
import { randomUUID } from 'node:crypto'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import App from '../App'
import { TOKEN_KEY } from './tokenStorage'

// Opt in only through scripts/verify_auth.py, which owns the server and cleanup.
it.skipIf(process.env.RUN_AUTH_INTEGRATION !== '1')(
  'real PostgreSQL registration, login, restore, logout and unauthorized cases',
  async () => {
    const base = process.env.AUTH_TEST_BASE_URL!
    const username = process.env.AUTH_TEST_USERNAME!
    const email = process.env.AUTH_TEST_EMAIL!
    const password = randomUUID()
    const nativeFetch = globalThis.fetch
    const results: Array<{ path: string; status: number }> = []
    vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
      const response = await nativeFetch(...args)
      results.push({ path: new URL(String(args[0])).pathname, status: response.status })
      return response
    })
    vi.stubEnv('VITE_API_BASE_URL', base)
    window.history.replaceState(null, '', '/register')
    let view = render(<App />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: username } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Account created. Please sign in.', {}, { timeout: 10_000 })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByText(username, {}, { timeout: 10_000 })).toBeInTheDocument()
    expect(screen.getByText(email)).toBeInTheDocument()
    expect(Boolean(sessionStorage.getItem(TOKEN_KEY))).toBe(true)
    expect(document.body.textContent?.includes(sessionStorage.getItem(TOKEN_KEY)!)).toBe(false)
    view.unmount()
    view = render(<App />)
    expect(await screen.findByText(username, {}, { timeout: 10_000 })).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('navigation')).getByRole('button', { name: 'Log out' }))
    await waitFor(() => expect(window.location.pathname).toBe('/'))
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    view.unmount()
    window.history.replaceState(null, '', '/account')
    view = render(<App />)
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()

    const wrong = await fetch(`${base}/api/v1/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password: `${password}wrong` }),
    })
    expect(wrong.status).toBe(401)
    expect((await fetch(`${base}/api/v1/auth/me`)).status).toBe(401)
    expect((await fetch(`${base}/api/v1/auth/me`, {
      headers: { Authorization: 'Bearer invalid-test-token' },
    })).status).toBe(401)
    expect(results).toEqual(expect.arrayContaining([
      { path: '/api/v1/auth/register', status: 201 },
      { path: '/api/v1/auth/login', status: 200 },
      { path: '/api/v1/auth/me', status: 200 },
      { path: '/api/v1/auth/login', status: 401 },
      { path: '/api/v1/auth/me', status: 401 },
    ]))
    view.unmount()
  }, 30_000,
)
