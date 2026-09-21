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
  if (typeof body !== 'object' || body === null ||
    !('access_token' in body) || typeof body.access_token !== 'string' || !body.access_token.trim() ||
    !('token_type' in body) || body.token_type !== 'bearer') {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected sign-in response.')
  }
  return { access_token: body.access_token, token_type: body.token_type }
}

export async function getCurrentUser(accessToken: string, signal?: AbortSignal): Promise<User> {
  return parseUser(await apiFetch<unknown>('/api/v1/auth/me', { accessToken, signal }))
}
