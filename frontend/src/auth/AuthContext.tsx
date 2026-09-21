import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import * as authApi from '../api/auth'
import { ApiError, apiFetch } from '../api/client'
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
    clearSession()
  }, [clearSession])

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
      const user = await authApi.getCurrentUser(saved, controller.signal)
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
  }, [clearSession])

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
      if (error instanceof ApiError && error.status === 401 &&
        token.current === credential && operation.current === currentOperation) {
        logout()
      }
      throw error
    }
  }, [logout])

  return <AuthContext.Provider value={{ state, login, logout, restore, request }}>
    {children}
  </AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth requires AuthProvider.')
  return auth
}
