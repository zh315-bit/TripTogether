import { ApiError } from '../api/client'

export const TOKEN_KEY = 'triptogether.accessToken'
/** The opaque refresh token from login; exchanged once at /auth/refresh when the access token expires. */
export const REFRESH_KEY = 'triptogether.refreshToken'

export const tokenStorage = {
  read(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY)
    } catch {
      throw new ApiError(0, 'STORAGE_ERROR', 'Browser session storage is unavailable.')
    }
  },
  write(token: string): void {
    try {
      sessionStorage.setItem(TOKEN_KEY, token)
    } catch {
      throw new ApiError(0, 'STORAGE_ERROR', 'Allow browser session storage to sign in.')
    }
  },
  readRefresh(): string | null {
    try {
      return sessionStorage.getItem(REFRESH_KEY)
    } catch {
      return null
    }
  },
  writeRefresh(token: string | null): void {
    try {
      if (token) sessionStorage.setItem(REFRESH_KEY, token)
      else sessionStorage.removeItem(REFRESH_KEY)
    } catch {
      // A refresh token is a convenience; the session still works until the access token expires.
    }
  },
  clear(): void {
    try {
      sessionStorage.removeItem(REFRESH_KEY)
      sessionStorage.removeItem(TOKEN_KEY)
    } catch {
      throw new ApiError(0, 'STORAGE_ERROR', 'Could not clear browser storage. Close this tab to end the session.')
    }
  },
}
