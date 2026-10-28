import { describe, expect, it, vi } from 'vitest'
import { getHealth } from './client'
import { forgotPassword, getCurrentUser, login, logout, refresh, register, resetPassword } from './auth'

const user = { id: 1, username: 'reader', email: 'reader@example.com', created_at: '2026-09-20T00:00:00Z' }

describe('Auth API contracts', () => {
  it('registers with JSON and returns only User fields', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(user), { status: 201 }))
    vi.stubGlobal('fetch', fetcher)
    const payload = { username: 'reader', email: user.email, password: 'disposable-test-input' }
    await expect(register(payload)).resolves.toEqual(user)
    expect(fetcher.mock.calls[0][0]).toBe('http://backend.test/api/v1/auth/register')
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(payload)
    expect(fetcher.mock.calls[0][1].headers.get('Content-Type')).toBe('application/json')
    expect(fetcher.mock.calls[0][1].headers.has('Authorization')).toBe(false)
  })

  it('uses JSON login, never OAuth form data', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"access_token":"opaque-test-token","token_type":"bearer"}'))
    vi.stubGlobal('fetch', fetcher)
    await expect(login({ email: user.email, password: ' test input ' })).resolves.toMatchObject({ token_type: 'bearer' })
    expect(fetcher.mock.calls[0][0]).toContain('/api/v1/auth/login')
    expect(JSON.parse(fetcher.mock.calls[0][1].body).password).toBe(' test input ')
  })

  it('adds Bearer only to the authenticated request; public health remains public', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(user)))
      .mockResolvedValueOnce(new Response('{"status":"ok"}'))
    vi.stubGlobal('fetch', fetcher)
    await getCurrentUser('opaque-test-token')
    await getHealth()
    expect(fetcher.mock.calls[0][1].headers.get('Authorization')).toBe('Bearer opaque-test-token')
    expect(fetcher.mock.calls[0][1].credentials).toBe('omit')
    expect(fetcher.mock.calls[0][1].redirect).toBe('error')
    expect(fetcher.mock.calls[1][1].headers.has('Authorization')).toBe(false)
  })

  it.each(['{}', '{"access_token":"","token_type":"bearer"}', '{"access_token":"x","token_type":"cookie"}'])(
    'rejects malformed token responses: %s', async (body) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)))
      await expect(login({ email: user.email, password: 'test-input' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    },
  )

  it('rejects malformed current user data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"id":"1"}')))
    await expect(getCurrentUser('opaque-test-token')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('preserves a 401 error for the auth layer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      '{"error":{"code":"INVALID_CREDENTIALS","message":"Invalid credentials","details":[]}}', { status: 401 },
    )))
    await expect(getCurrentUser('opaque-test-token')).rejects.toMatchObject({ status: 401, code: 'INVALID_CREDENTIALS' })
  })
})


describe('session and password reset adapters', () => {
  it('keeps the refresh token from login and exchanges it at /auth/refresh', async () => {
    const pair = { access_token: 'a1', token_type: 'bearer', refresh_token: 'r1' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(pair))))
    await expect(login({ email: user.email, password: 'x' })).resolves.toEqual(pair)
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...pair, access_token: 'a2', refresh_token: 'r2' })))
    vi.stubGlobal('fetch', fetcher)
    await expect(refresh('r1')).resolves.toEqual({ ...pair, access_token: 'a2', refresh_token: 'r2' })
    expect(fetcher.mock.calls[0][0]).toBe('http://backend.test/api/v1/auth/refresh')
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ refresh_token: 'r1' })
    expect(fetcher.mock.calls[0][1].headers.has('Authorization')).toBe(false)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...pair, refresh_token: 5 }))))
    await expect(refresh('r1')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('posts logout, forgot and reset bodies to their routes', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    await expect(logout('r1')).resolves.toBeUndefined()
    await expect(resetPassword('tok', 'a-new-password')).resolves.toBeUndefined()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'accepted' }), { status: 202 })))
    await expect(forgotPassword('reader@example.com')).resolves.toBeUndefined()
    expect(fetcher.mock.calls.map(([url]) => String(url))).toEqual([
      'http://backend.test/api/v1/auth/logout', 'http://backend.test/api/v1/auth/password/reset',
    ])
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ token: 'tok', password: 'a-new-password' })
  })
})
