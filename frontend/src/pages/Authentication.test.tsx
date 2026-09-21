import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { TOKEN_KEY } from '../auth/tokenStorage'

const user = { id: 7, username: 'reader', email: 'reader@example.com', created_at: '2026-09-20T00:00:00Z' }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const failure = (status: number, code: string, message: string, details: unknown[] = []) =>
  json({ error: { code, message, details } }, status)
function mount(path: string) {
  window.history.replaceState(null, '', path)
  return render(<App />)
}
function fill(registering = false) {
  if (registering) fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'reader' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: user.email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: ' local-test-input ' } })
}

describe('Register and login pages', () => {
  it('renders labelled registration fields with autocomplete', () => {
    mount('/register')
    expect(screen.getByLabelText('Username')).toHaveAttribute('autocomplete', 'username')
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email')
    expect(screen.getByLabelText('Password')).toHaveAttribute('autocomplete', 'new-password')
  })

  it('registers, then navigates to login with success feedback and no token', async () => {
    const fetcher = vi.fn().mockResolvedValue(json(user, 201))
    vi.stubGlobal('fetch', fetcher)
    mount('/register')
    fill(true)
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Account created. Please sign in.')).toBeInTheDocument()
    expect(window.location.pathname).toBe('/login')
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(screen.getByLabelText('Password')).toHaveValue('')
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      username: 'reader', email: user.email, password: ' local-test-input ',
    })
  })

  it.each([
    ['EMAIL_ALREADY_EXISTS', 'Email already registered', 'Email'],
    ['USERNAME_ALREADY_EXISTS', 'Username already registered', 'Username'],
  ])('shows %s near its field', async (code, message, field) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failure(409, code, message)))
    mount('/register')
    fill(true)
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByLabelText(field)).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Password')).toHaveValue('')
  })

  it('maps server validation details and renders them as text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failure(422, 'VALIDATION_ERROR', 'Request validation failed',
      [{ loc: ['body', 'email'], msg: '<script>not valid</script>', type: 'value_error' }])))
    mount('/register')
    fill(true)
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('<script>not valid</script>')).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
  })

  it('validates required fields before sending a request', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    mount('/register')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Please check')
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('shows a registration service outage with safe feedback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failure(503, 'REGISTRATION_UNAVAILABLE', 'Registration temporarily unavailable')))
    mount('/register')
    fill(true)
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Registration temporarily unavailable')
    expect(screen.getByLabelText('Password')).toHaveValue('')
  })

  it('shows registration loading and prevents duplicate submissions', async () => {
    let resolve!: (response: Response) => void
    const fetcher = vi.fn(() => new Promise<Response>((done) => { resolve = done }))
    vi.stubGlobal('fetch', fetcher)
    mount('/register')
    fill(true)
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    const button = screen.getByRole('button', { name: 'Creating account...' })
    expect(button).toBeDisabled()
    await userEvent.click(button)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await act(async () => resolve(json(user, 201)))
  })

  it('logs in, checks me, shows account and restores across a remount', async () => {
    const fetcher = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith('/login')) return json({ access_token: 'opaque-test-token', token_type: 'bearer' })
      return json(user)
    })
    vi.stubGlobal('fetch', fetcher)
    const view = mount('/login')
    fill()
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('heading', { name: 'Trips' })).toBeInTheDocument()
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('opaque-test-token')
    expect(document.body.textContent).not.toContain('opaque-test-token')
    expect(localStorage.length).toBe(0)
    expect(fetcher.mock.calls[1][1].headers.get('Authorization')).toBe('Bearer opaque-test-token')
    view.unmount()
    window.history.replaceState(null, '', '/account')
    mount('/account')
    expect((await screen.findAllByText(user.username)).length).toBeGreaterThan(0)
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/me'))).toHaveLength(2)
  })

  it('shows pending login through the me request, not just through token receipt', async () => {
    let resolve!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith('/login')) return json({ access_token: 'candidate-token', token_type: 'bearer' })
      return new Promise<Response>((done) => { resolve = done })
    }))
    mount('/login')
    fill()
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(screen.getByRole('button', { name: 'Signing in...' })).toBeDisabled()
    expect(screen.queryByRole('heading', { name: 'Trips' })).not.toBeInTheDocument()
    await act(async () => resolve(json(user)))
    expect(await screen.findByRole('heading', { name: 'Trips' })).toBeInTheDocument()
  })

  it.each([
    [401, 'INVALID_CREDENTIALS', 'Invalid email or password'],
    [503, 'AUTHENTICATION_UNAVAILABLE', 'Authentication temporarily unavailable'],
  ])('handles login HTTP %s safely', async (status, code, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failure(status as number, code as string, message as string)))
    mount('/login')
    fill()
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message as string)
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(screen.getByLabelText('Password')).toHaveValue('')
  })

  it('shows login network failure without crashing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError()))
    mount('/login')
    fill()
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The backend could not be reached.')
  })

  it('redirects unauthenticated account visits to login', async () => {
    mount('/account')
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/login')
  })

  it('waits for restore before rendering protected content', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    let resolve!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((done) => { resolve = done })))
    mount('/account')
    expect(screen.getByRole('status')).toHaveTextContent('Checking session...')
    expect(screen.queryByRole('heading', { name: 'Your account' })).not.toBeInTheDocument()
    await act(async () => resolve(json(user)))
    expect(await screen.findByRole('heading', { name: 'Your account' })).toBeInTheDocument()
  })

  it('logs out locally, navigates home and removes the credential', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    const fetcher = vi.fn().mockImplementation(async (url: string) => json(url.endsWith('/health') ? { status: 'ok' } : user))
    vi.stubGlobal('fetch', fetcher)
    mount('/account')
    await screen.findByRole('heading', { name: 'Your account' })
    await userEvent.click(within(screen.getByRole('navigation')).getByRole('button', { name: 'Log out' }))
    await waitFor(() => expect(window.location.pathname).toBe('/'))
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(screen.queryByText(user.email)).not.toBeInTheDocument()
    expect(fetcher.mock.calls.some(([url]) => url.includes('/logout'))).toBe(false)
  })
})
