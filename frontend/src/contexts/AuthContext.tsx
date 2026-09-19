import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import api from '@/api/client'

export type Mode = 'candidate' | 'recruiter'

interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'candidate' | 'recruiter' | ''
  /** One-way recruiter capability; absent on pre-flag backends. */
  is_recruiter?: boolean
  avatar_url?: string
}

interface AuthContextType {
  user: User | null
  token: string | null
  loading: boolean
  /** Which side of the app is being viewed (Upwork-style toggle), persisted per browser. */
  mode: Mode
  setMode: (mode: Mode) => void
  login: (provider: 'google' | 'github') => void
  logout: () => void
  setAuth: (token: string, user: User) => void
}

const AuthContext = createContext<AuthContextType | null>(null)

const TOKEN_KEY = 'aura_token'
const MODE_KEY = 'aura_active_role'

function canBeRecruiter(user: User | null): boolean {
  return !!user && (user.role === 'admin' || user.role === 'recruiter' || !!user.is_recruiter)
}

function resolveMode(user: User | null): Mode {
  const stored = localStorage.getItem(MODE_KEY)
  if (stored === 'candidate' || stored === 'recruiter') {
    // A stored recruiter mode is only honoured while the capability exists.
    if (stored === 'candidate' || canBeRecruiter(user)) return stored
  }
  return canBeRecruiter(user) ? 'recruiter' : 'candidate'
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [loading, setLoading] = useState(true)
  const [mode, setModeState] = useState<Mode>(() =>
    localStorage.getItem(MODE_KEY) === 'recruiter' ? 'recruiter' : 'candidate'
  )

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }
    api.get('/auth/me')
      .then(res => {
        setUser(res.data)
        setModeState(resolveMode(res.data))
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY)
        setToken(null)
        setUser(null)
        setModeState('candidate')
      })
      .finally(() => setLoading(false))
  }, [token])

  const login = useCallback((provider: 'google' | 'github') => {
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    window.location.href = `${baseUrl}/auth/${provider}`
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const setAuth = useCallback((newToken: string, newUser: User) => {
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
    setUser(newUser)
    setModeState(resolveMode(newUser))
  }, [])

  const setMode = useCallback((next: Mode) => {
    localStorage.setItem(MODE_KEY, next)
    setModeState(next)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, loading, mode, setMode, login, logout, setAuth }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
