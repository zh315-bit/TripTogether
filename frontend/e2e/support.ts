import { randomUUID } from 'node:crypto'
import { expect, type APIRequestContext, type Browser, type Page } from '@playwright/test'

export const API = process.env.E2E_API_URL ?? 'http://127.0.0.1:8011'
const TOKEN_KEY = 'triptogether.accessToken'

export type User = { id: number; username: string; email: string; password: string; token: string }
export type Trip = { id: number; name: string; start_date: string; end_date: string }

/** Unique, username-safe suffix so parallel workers never collide on the shared database. */
export function unique(prefix: string): string {
  return `${prefix}${randomUUID().replace(/-/g, '').slice(0, 10)}`
}

export const auth = (token: string) => ({ Authorization: `Bearer ${token}` })

export async function api<T = unknown>(
  request: APIRequestContext, token: string, method: 'GET' | 'POST' | 'PATCH' | 'DELETE', path: string, data?: unknown,
): Promise<T> {
  const response = await request.fetch(`${API}/api/v1${path}`, { method, headers: auth(token), data })
  expect(response.ok(), `${method} ${path} -> ${response.status()} ${await response.text()}`).toBeTruthy()
  return response.status() === 204 ? (undefined as T) : response.json()
}

/** A fresh account created through the public API; the password never leaves the test process. */
export async function registerUser(request: APIRequestContext, name: string): Promise<User> {
  const username = unique(name)
  const email = `${username.toLowerCase()}@example.com`
  const password = `Pw-${unique('a')}-${unique('b')}`
  const registered = await request.post(`${API}/api/v1/auth/register`, { data: { username, email, password } })
  expect(registered.ok(), await registered.text()).toBeTruthy()
  const login = await request.post(`${API}/api/v1/auth/login`, { data: { email, password } })
  expect(login.ok(), await login.text()).toBeTruthy()
  const { access_token: token } = await login.json()
  const me = await api<{ id: number }>(request, token, 'GET', '/auth/me')
  return { id: me.id, username, email, password, token }
}

export async function createTrip(
  request: APIRequestContext, owner: User, name = unique('Trip'), start_date = '2027-06-10', end_date = '2027-06-12',
): Promise<Trip> {
  return api<Trip>(request, owner.token, 'POST', '/trips', { name, destination: 'Kyoto, Japan', start_date, end_date })
}

export async function addMember(request: APIRequestContext, owner: User, trip: Trip, member: User): Promise<void> {
  const invitation = await api<{ id: number }>(request, owner.token, 'POST', `/trips/${trip.id}/invitations`, { email: member.email })
  await api(request, member.token, 'POST', `/invitations/${invitation.id}/accept`)
}

/** A browser context already signed in as the user, the way the app stores its session. */
export async function signedInPage(browser: Browser, user: User): Promise<Page> {
  const context = await browser.newContext()
  await context.addInitScript(([key, token]) => { sessionStorage.setItem(key, token) }, [TOKEN_KEY, user.token])
  return context.newPage()
}

export async function openPanel(page: Page, tripId: number, panel: string): Promise<void> {
  await page.goto(`/trips/${tripId}?panel=${panel}`)
  await expect(page.getByRole('status').filter({ hasText: /^Live$/ })).toBeVisible()
}
