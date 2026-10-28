import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import * as authApi from '../api/auth'
import { ApiError, apiFetch, apiStream } from '../api/client'
import type { LoginRequest, User } from '../types/auth'
import { tokenStorage } from './tokenStorage'

type AuthState =
  | { status: 'loading' | 'anonymous'; user: null }
  | { status: 'authenticated'; user: User }
  | { status: 'error'; user: null; message: string }

type AuthContextValue = {
  state: AuthState
  login: (payload: LoginRequest, signal: AbortSignal) => Promise<void>
  logout: () => void
  restore: () => Promise<void>
  request: <T>(path: string, init?: RequestInit) => Promise<T>
  /** Opens an authenticated event stream; a 401 ends the session like any other request. */
  stream: (path: string, signal: AbortSignal) => Promise<Response>
}

const AuthContext = createContext<AuthContextValue | null>(null)
const anonymous: AuthState = { status: 'anonymous', user: null }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', user: null })
  const token = useRef<string | null>(null)
  const operation = useRef<AbortController | null>(null)

  const clearSession = useCallback(() => {
    token.current = null
    try {
      tokenStorage.clear()
      setState(anonymous)
    } catch (error) {
      setState({ status: 'error', user: null, message: (error as ApiError).message })
    }
  }, [])

  const logout = useCallback(() => {
    operation.current?.abort()
    const refreshToken = tokenStorage.readRefresh()
    // Revoke the server-side session too; the local one ends either way.
    if (refreshToken) void authApi.logout(refreshToken).catch(() => undefined)
    clearSession()
  }, [clearSession])

  // One refresh at a time: concurrent 401s share the exchange instead of each spending the token.
  const refreshing = useRef<Promise<string> | null>(null)
  const refreshSession = useCallback((): Promise<string> => {
    if (refreshing.current) return refreshing.current
    const refreshToken = tokenStorage.readRefresh()
    if (!refreshToken) return Promise.reject(new ApiError(401, 'INVALID_CREDENTIALS', 'Please log in.'))
    const exchange = (async () => {
      const pair = await authApi.refresh(refreshToken)
      tokenStorage.write(pair.access_token)
      tokenStorage.writeRefresh(pair.refresh_token ?? null)
      token.current = pair.access_token
      return pair.access_token
    })().finally(() => { refreshing.current = null })
    refreshing.current = exchange
    return exchange
  }, [])

  const restore = useCallback(async () => {
    operation.current?.abort()
    const controller = new AbortController()
    operation.current = controller
    setState({ status: 'loading', user: null })
    try {
      const saved = tokenStorage.read()
      token.current = saved
      if (!saved) {
        setState(anonymous)
        return
      }
      let user: User
      try {
        user = await authApi.getCurrentUser(saved, controller.signal)
      } catch (error) {
        // An expired access token is routine: exchange the refresh token and look again.
        if (!(error instanceof ApiError && error.status === 401) || !tokenStorage.readRefresh()) throw error
        const renewed = await refreshSession()
        user = await authApi.getCurrentUser(renewed, controller.signal)
      }
      if (!controller.signal.aborted) setState({ status: 'authenticated', user })
    } catch (error) {
      if (controller.signal.aborted) return
      if (error instanceof ApiError && error.status === 401) {
        clearSession()
      } else {
        setState({
          status: 'error', user: null,
          message: error instanceof ApiError ? error.message : 'Could not check your session.',
        })
      }
    }
  }, [clearSession, refreshSession])

  useEffect(() => {
    void restore()
    return () => operation.current?.abort()
  }, [restore])

  const login = useCallback(async (payload: LoginRequest, signal: AbortSignal) => {
    operation.current?.abort()
    const controller = new AbortController()
    operation.current = controller
    const combined = AbortSignal.any([controller.signal, signal])
    try {
      const response = await authApi.login(payload, combined)
      combined.throwIfAborted()
      tokenStorage.write(response.access_token)
      tokenStorage.writeRefresh(response.refresh_token ?? null)
      token.current = response.access_token
      const user = await authApi.getCurrentUser(response.access_token, combined)
      combined.throwIfAborted()
      setState({ status: 'authenticated', user })
    } catch (error) {
      // An older request cannot clear a newer session or revive one after logout.
      if (operation.current === controller && !controller.signal.aborted) clearSession()
      throw error
    }
  }, [clearSession])

  const request = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const credential = token.current
    const currentOperation = operation.current
    if (!credential) throw new ApiError(401, 'INVALID_CREDENTIALS', 'Please log in.')
    try {
      return await apiFetch<T>(path, { ...init, accessToken: credential })
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401) ||
        token.current !== credential || operation.current !== currentOperation) {
        throw error
      }
      if (tokenStorage.readRefresh()) {
        // The access token expired mid-session: renew it once and retry the same request.
        try {
          const renewed = await refreshSession()
          return await apiFetch<T>(path, { ...init, accessToken: renewed })
        } catch (retryError) {
          if (!(retryError instanceof ApiError && retryError.status === 401)) throw retryError
        }
      }
      if (operation.current === currentOperation) logout()
      throw error
    }
  }, [logout, refreshSession])

  const stream = useCallback(async (path: string, signal: AbortSignal): Promise<Response> => {
    const credential = token.current
    const currentOperation = operation.current
    if (!credential) throw new ApiError(401, 'INVALID_CREDENTIALS', 'Please log in.')
    try {
      return await apiStream(path, { accessToken: credential, signal })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401 &&
        token.current === credential && operation.current === currentOperation) {
        logout()
      }
      throw error
    }
  }, [logout])

  return <AuthContext.Provider value={{ state, login, logout, restore, request, stream }}>
    {children}
  </AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth requires AuthProvider.')
  return auth
}
