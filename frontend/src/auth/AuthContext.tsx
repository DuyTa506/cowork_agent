import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi, setUnauthorizedHandler, type User } from '../api'
import { clearToken, getToken, setToken } from './tokenStorage'

type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

interface AuthValue {
  status: AuthStatus
  /** The signed-in user; null unless `status` is `authenticated`. */
  user: User | null
  /** Signs in and stores the token for this tab. Throws `ApiError` on bad credentials. */
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

/** Holds the session: restores it from the stored token on load and drops it when the server answers 401. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>(getToken() ? 'loading' : 'anonymous')

  const endSession = useCallback(() => {
    clearToken()
    setUser(null)
    setStatus('anonymous')
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(endSession)
    return () => setUnauthorizedHandler(null)
  }, [endSession])

  useEffect(() => {
    if (!getToken()) return
    const controller = new AbortController()
    authApi
      .fetchCurrentUser(controller.signal)
      .then((current) => {
        setUser(current)
        setStatus('authenticated')
      })
      .catch(() => {
        if (!controller.signal.aborted) endSession()
      })
    return () => controller.abort()
  }, [endSession])

  const login = useCallback(async (username: string, password: string) => {
    const result = await authApi.login(username, password)
    setToken(result.access_token)
    setUser(result.user)
    setStatus('authenticated')
  }, [])

  const value = useMemo<AuthValue>(() => ({ status, user, login, logout: endSession }), [status, user, login, endSession])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** The session state and actions; must be used under `AuthProvider`. */
export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
