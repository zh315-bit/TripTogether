import type {
  ApiErrorPayload,
  ApiValidationIssue,
  HealthResponse,
} from '../types/api'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: ApiValidationIssue[]
  /** Seconds from a Retry-After header (429/503), when the server sent one. */
  readonly retryAfter: number | null
  /** The server's X-Request-ID, so a report can be matched to one access-log line. */
  readonly requestId: string | null

  constructor(
    status: number,
    code: string,
    message: string,
    details: ApiValidationIssue[] = [],
    retryAfter: number | null = null,
    requestId: string | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.retryAfter = retryAfter
    this.requestId = requestId
  }
}

function parseRetryAfter(value: string | null): number | null {
  // Only the delay-seconds form; the backend never sends an HTTP date.
  if (!value || !/^[0-9]{1,4}$/.test(value.trim())) return null
  return Number(value.trim())
}

function getBaseUrl(): string {
  try {
    const value = import.meta.env.VITE_API_BASE_URL?.trim()
    if (!value) throw new Error()
    const url = new URL(value)
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username || url.password || url.search || url.hash ||
      url.pathname !== '/'
    ) throw new Error()
    return url.origin
  } catch {
    throw new ApiError(0, 'CONFIG_ERROR', 'Set VITE_API_BASE_URL to the backend origin.')
  }
}

function isApiErrorPayload(body: unknown): body is ApiErrorPayload {
  if (!body || typeof body !== 'object' || !('error' in body)) {
    return false
  }

  const error = body.error
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    'message' in error &&
    typeof error.code === 'string' &&
    typeof error.message === 'string' &&
    'details' in error &&
    Array.isArray(error.details) &&
    error.details.every((issue: unknown) => (
      typeof issue === 'object' && issue !== null &&
      'loc' in issue && Array.isArray(issue.loc) &&
      issue.loc.every((part: unknown) => typeof part === 'string' || typeof part === 'number') &&
      'msg' in issue && typeof issue.msg === 'string' &&
      'type' in issue && typeof issue.type === 'string'
    ))
  )
}

export type ApiRequestOptions = RequestInit & { accessToken?: string }

/** The error the backend's JSON envelope describes, or a generic one for any other failure body. */
async function errorFromResponse(response: Response): Promise<ApiError> {
  return errorFromBody(response, await response.json().catch(() => null))
}

function errorFromBody(response: Response, body: unknown): ApiError {
  const requestId = response.headers.get('X-Request-ID')
  if (isApiErrorPayload(body)) {
    return new ApiError(
      response.status, body.error.code, body.error.message, body.error.details,
      parseRetryAfter(response.headers.get('Retry-After')), requestId,
    )
  }
  return new ApiError(
    response.status, 'HTTP_ERROR', `The backend returned HTTP ${response.status}.`, [], null, requestId)
}

/**
 * Opens a long-lived text/event-stream response with the same base URL, Bearer
 * header and error envelope as apiFetch, but without its request timeout. The
 * caller reads `response.body` and aborts `signal` to close the connection.
 */
export async function apiStream(path: string, options: ApiRequestOptions & { signal: AbortSignal }): Promise<Response> {
  const { accessToken, signal, ...init } = options
  const baseUrl = getBaseUrl()
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    throw new ApiError(0, 'CONFIG_ERROR', 'API paths must start with a single slash.')
  }
  const headers = new Headers(init.headers)
  headers.set('Accept', 'text/event-stream')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init, headers, signal, credentials: 'omit', redirect: 'error', cache: 'no-store',
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new ApiError(0, 'NETWORK_ERROR', 'The backend could not be reached.')
  }
  if (!response.ok) throw await errorFromResponse(response)
  if (!(response.headers.get('Content-Type') ?? '').startsWith('text/event-stream') || !response.body) {
    throw new ApiError(response.status, 'INVALID_RESPONSE', 'Expected an event stream.')
  }
  return response
}

export async function apiFetch<T>(
  path: string,
  options?: ApiRequestOptions,
): Promise<T> {
  const { accessToken, ...init } = options ?? {}
  const baseUrl = getBaseUrl()
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    throw new ApiError(0, 'CONFIG_ERROR', 'API paths must start with a single slash.')
  }
  const headers = new Headers(init?.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const timeout = AbortSignal.timeout(10_000)
  const signal = init?.signal
    ? AbortSignal.any([init.signal, timeout])
    : timeout

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init, headers, signal, credentials: 'omit', redirect: 'error',
      ...(accessToken ? { cache: 'no-store' as const } : {}),
    })
    if (response.status === 204) return undefined as T
    const body: unknown = await response.json().catch(() => null)
    if (signal.aborted) throw signal.reason
    if (!response.ok) throw errorFromBody(response, body)
    if (body === null) {
      throw new ApiError(response.status, 'INVALID_RESPONSE', 'Expected a JSON response.')
    }
    // A generic type is not runtime validation; endpoint adapters validate as needed.
    return body as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (init?.signal?.aborted) throw error
    if (timeout.aborted) {
      throw new ApiError(0, 'TIMEOUT', 'The backend request timed out.')
    }
    throw new ApiError(0, 'NETWORK_ERROR', 'The backend could not be reached.')
  }
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const body = await apiFetch<unknown>('/health', { signal })
  if (typeof body !== 'object' || body === null || !('status' in body) || body.status !== 'ok') {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected health response.')
  }
  return { status: 'ok' }
}
