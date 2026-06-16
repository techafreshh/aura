import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import api from '@/api/client'

interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'candidate'
  avatar_url?: string
}

interface AuthContextType {
  user: User | null
  token: string | null
  loading: boolean
  login: (provider: 'google' | 'github') => void
  logout: () => void
  setAuth: (token: string, user: User) => void
}

const AuthContext = createContext<AuthContextType | null>(null)

const TOKEN_KEY = 'aura_token'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }
    api.get('/auth/me')
      .then(res => setUser(res.data))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY)
        setToken(null)
        setUser(null)
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
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, setAuth }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
