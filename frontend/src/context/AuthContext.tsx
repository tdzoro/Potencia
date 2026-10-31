/**
 * Authentication state for the whole app.
 *
 * The access token lives in storage, but the *user* is re-fetched on load: a
 * stale token that no longer authenticates must sign the user out rather than
 * render a dashboard full of failed requests.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { currentUser, login as loginRequest, logout as logoutRequest, register as registerRequest } from '../services/auth'
import { readSession } from '../services/client'
import type { User } from '../types/domain'

interface AuthContextValue {
  user: User | null
  status: 'loading' | 'authenticated' | 'anonymous'
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<'loading' | 'authenticated' | 'anonymous'>('loading')

  useEffect(() => {
    let cancelled = false

    async function bootstrap(): Promise<void> {
      if (!readSession()) {
        if (!cancelled) {
          setStatus('anonymous')
        }
        return
      }
      try {
        const me = await currentUser()
        if (!cancelled) {
          setUser(me)
          setStatus('authenticated')
        }
      } catch {
        if (!cancelled) {
          setUser(null)
          setStatus('anonymous')
        }
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const me = await loginRequest({ email, password })
    setUser(me)
    setStatus('authenticated')
  }, [])

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    const response = await registerRequest({ email, password, display_name: displayName })
    setUser(response.user)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    await logoutRequest()
    setUser(null)
    setStatus('anonymous')
  }, [])

  const refreshUser = useCallback(async () => {
    setUser(await currentUser())
    setStatus('authenticated')
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, register, logout, refreshUser }),
    [user, status, login, register, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside an AuthProvider.')
  }
  return context
}
