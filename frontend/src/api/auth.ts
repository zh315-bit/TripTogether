import { ApiError, apiFetch } from './client'
import type { LoginRequest, RegisterRequest, TokenResponse, User } from '../types/auth'

function parseUser(body: unknown): User {
  if (typeof body !== 'object' || body === null ||
    !('id' in body) || typeof body.id !== 'number' || !Number.isInteger(body.id) || body.id <= 0 ||
    !('username' in body) || typeof body.username !== 'string' ||
    !('email' in body) || typeof body.email !== 'string' ||
    !('created_at' in body) || typeof body.created_at !== 'string') {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected account response.')
  }
  return { id: body.id, username: body.username, email: body.email, created_at: body.created_at }
}

export async function register(payload: RegisterRequest, signal?: AbortSignal): Promise<User> {
  return parseUser(await apiFetch<unknown>('/api/v1/auth/register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal, cache: 'no-store',
  }))
}

export async function login(payload: LoginRequest, signal?: AbortSignal): Promise<TokenResponse> {
  const body = await apiFetch<unknown>('/api/v1/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal, cache: 'no-store',
  })
  return parseTokens(body)
}

function parseTokens(body: unknown): TokenResponse {
  if (typeof body !== 'object' || body === null ||
    !('access_token' in body) || typeof body.access_token !== 'string' || !body.access_token.trim() ||
    !('token_type' in body) || body.token_type !== 'bearer' ||
    ('refresh_token' in body && typeof body.refresh_token !== 'string')) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected sign-in response.')
  }
  const refresh = 'refresh_token' in body && body.refresh_token ? String(body.refresh_token) : undefined
  return { access_token: body.access_token, token_type: body.token_type, ...(refresh ? { refresh_token: refresh } : {}) }
}

/** Exchanges a refresh token for a new pair; a 401 means the session is over. */
export async function refresh(refreshToken: string, signal?: AbortSignal): Promise<TokenResponse> {
  return parseTokens(await apiFetch<unknown>('/api/v1/auth/refresh', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }), signal, cache: 'no-store',
  }))
}

/** Revokes the refresh session; errors are the caller's to ignore. */
export function logout(refreshToken: string, signal?: AbortSignal): Promise<void> {
  return apiFetch<void>('/api/v1/auth/logout', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }), signal, cache: 'no-store',
  })
}

/** Always resolves on 202, whether or not the address is registered. */
export async function forgotPassword(email: string, signal?: AbortSignal): Promise<void> {
  await apiFetch<unknown>('/api/v1/auth/password/forgot', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }), signal, cache: 'no-store',
  })
}

export function resetPassword(token: string, password: string, signal?: AbortSignal): Promise<void> {
  return apiFetch<void>('/api/v1/auth/password/reset', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }), signal, cache: 'no-store',
  })
}

export async function getCurrentUser(accessToken: string, signal?: AbortSignal): Promise<User> {
  return parseUser(await apiFetch<unknown>('/api/v1/auth/me', { accessToken, signal }))
}
