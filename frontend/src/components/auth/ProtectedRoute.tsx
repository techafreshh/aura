import { Navigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import type { ReactNode } from 'react'

interface ProtectedRouteProps {
  children: ReactNode
  requireAdmin?: boolean
  requireRole?: 'recruiter' | 'candidate'
}

export function ProtectedRoute({ children, requireAdmin = false, requireRole }: ProtectedRouteProps) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <p>Loading...</p>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/" replace />
  }

  if (requireAdmin && user.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  // Users who have not picked a role yet go through the role picker first.
  // Admins pass recruiter-only routes (mirrors require_recruiter on the
  // backend), as do dual-role users granted the one-way is_recruiter flag.
  const canRecruit = user.role === 'recruiter' || user.role === 'admin' || !!user.is_recruiter
  const allowed = requireRole === 'recruiter' ? canRecruit : true
  if (requireRole && !allowed) {
    const target = user.role === '' ? '/choose-role' : '/'
    return <Navigate to={target} replace />
  }

  return <>{children}</>
}
