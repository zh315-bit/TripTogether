import type {
  ApiErrorPayload,
  ApiValidationIssue,
  HealthResponse,
} from '../types/api'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: ApiValidationIssue[]

  constructor(
    status: number,
    code: string,
    message: string,
    details: ApiValidationIssue[] = [],
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
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
    if (!response.ok) {
      if (isApiErrorPayload(body)) {
        throw new ApiError(
          response.status, body.error.code, body.error.message, body.error.details,
        )
      }
      throw new ApiError(
        response.status, 'HTTP_ERROR', `The backend returned HTTP ${response.status}.`,
      )
    }
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
