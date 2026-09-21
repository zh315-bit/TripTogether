import { ApiError } from '../api/client'

export const TOKEN_KEY = 'triptogether.accessToken'

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
  clear(): void {
    try {
      sessionStorage.removeItem(TOKEN_KEY)
    } catch {
      throw new ApiError(0, 'STORAGE_ERROR', 'Could not clear browser storage. Close this tab to end the session.')
    }
  },
}
