import { describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, getHealth } from './client'

function respond(body: string | null, status = 200) {
  const mock = vi.fn().mockResolvedValue(new Response(body, { status }))
  vi.stubGlobal('fetch', mock)
  return mock
}

describe('API client', () => {
  it('uses the configured origin and public health path', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://example.test/')
    const mock = respond('{"status":"ok"}')
    await expect(getHealth()).resolves.toEqual({ status: 'ok' })
    expect(mock).toHaveBeenCalledWith('https://example.test/health', expect.any(Object))
    expect(mock.mock.calls[0][1].headers.get('Accept')).toBe('application/json')
  })

  it.each(['', 'invalid', 'ftp://example.test', 'https://user:secret@example.test',
    'https://example.test/api/v1', 'https://example.test?query=yes'])(
    'rejects invalid origin configuration: %s', async (value) => {
      vi.stubEnv('VITE_API_BASE_URL', value)
      const mock = respond('{"status":"ok"}')
      await expect(getHealth()).rejects.toMatchObject({ code: 'CONFIG_ERROR' })
      expect(mock).not.toHaveBeenCalled()
    },
  )

  it('retains backend status, code, message and validation details', async () => {
    const details = [{ loc: ['body', 'email'], msg: 'Field required', type: 'missing' }]
    respond(JSON.stringify({ error: { code: 'VALIDATION_ERROR', message: 'Invalid', details } }), 422)
    await expect(apiFetch('/api/v1/auth/register')).rejects.toMatchObject({
      status: 422, code: 'VALIDATION_ERROR', message: 'Invalid', details,
    })
  })

  it.each([['1', 1], [' 30 ', 30], ['Wed, 21 Oct 2026 07:28:00 GMT', null], ['-1', null], [null, null]])(
    'reads a delay-seconds Retry-After header: %s', async (header, expected) => {
      const headers = header === null ? undefined : { 'Retry-After': header }
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
        error: { code: 'GEOCODER_BUSY', message: 'Busy', details: [] },
      }), { status: 429, headers })))
      await expect(apiFetch('/api/v1/geocode?q=x')).rejects.toMatchObject({
        status: 429, code: 'GEOCODER_BUSY', retryAfter: expected,
      })
    },
  )

  it('keeps the server request id so an error can be matched to its log line', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'RATE_LIMITED', message: 'Too many attempts; try again shortly', details: [] },
    }), { status: 429, headers: { 'X-Request-ID': 'req-7', 'Retry-After': '12' } })))
    await expect(apiFetch('/api/v1/auth/login')).rejects.toMatchObject({
      status: 429, code: 'RATE_LIMITED', retryAfter: 12, requestId: 'req-7',
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>', { status: 502 })))
    await expect(apiFetch('/api/v1/trips')).rejects.toMatchObject({ code: 'HTTP_ERROR', requestId: null })
  })

  it('converts transport failure into ApiError without retrying', async () => {
    const mock = vi.fn().mockRejectedValue(new TypeError())
    vi.stubGlobal('fetch', mock)
    const error = await getHealth().catch((value: unknown) => value)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
    expect(mock).toHaveBeenCalledTimes(1)
  })

  it('handles a non-JSON HTTP error', async () => {
    respond('<html>Bad gateway</html>', 502)
    await expect(getHealth()).rejects.toMatchObject({ status: 502, code: 'HTTP_ERROR' })
  })

  it('does not trust malformed error details', async () => {
    respond('{"error":{"code":"BAD","message":"Bad","details":[{"loc":null}]}}', 400)
    await expect(getHealth()).rejects.toMatchObject({ code: 'HTTP_ERROR', details: [] })
  })

  it.each(['not json', 'null', '{}', '{"status":"wrong"}'])(
    'rejects invalid successful health responses: %s', async (body) => {
      respond(body)
      await expect(getHealth()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    },
  )

  it('handles 204 without JSON decoding', async () => {
    respond(null, 204)
    await expect(apiFetch<void>('/api/v1/example', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('preserves caller Headers and JSON body', async () => {
    const mock = respond('{}')
    await apiFetch('/api/v1/example', {
      method: 'POST', headers: new Headers({ 'Content-Type': 'application/json' }),
      body: '{"name":"Example"}',
    })
    expect(mock.mock.calls[0][1].headers.get('Content-Type')).toBe('application/json')
    expect(mock.mock.calls[0][1].body).toBe('{"name":"Example"}')
  })

  it('preserves cancellation for effect cleanup', async () => {
    const controller = new AbortController()
    controller.abort()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(controller.signal.reason))
    await expect(getHealth(controller.signal)).rejects.toBe(controller.signal.reason)
  })

  it('reports timeout failures', async () => {
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(AbortSignal.abort())
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('Timeout')))
    await expect(getHealth()).rejects.toMatchObject({ code: 'TIMEOUT' })
  })

  it('rejects a backslash URL before sending any Bearer token', async () => {
    const mock = vi.fn()
    vi.stubGlobal('fetch', mock)
    await expect(apiFetch('/\\untrusted.test', { accessToken: 'test-token' })).rejects.toMatchObject({ code: 'CONFIG_ERROR' })
    expect(mock).not.toHaveBeenCalled()
  })
})
