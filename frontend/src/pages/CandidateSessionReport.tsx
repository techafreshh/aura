import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getReport, type FinalReport } from '@/api/client'
import { ReportView } from '@/components/interview/ReportView'
import { useAuth } from '@/contexts/AuthContext'
import { initials } from '@/lib/dashboard-utils'
import '@/styles/aura-dashboard.css'

export function CandidateSessionReport() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { sessionId } = useParams<{ sessionId: string }>()
  const [report, setReport] = useState<FinalReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setReport(null)
    setError(null)
    getReport(sessionId)
      .then(r => { if (!cancelled) setReport(r) })
      .catch(err => {
        if (cancelled) return
        console.error('Failed to load session report:', {
          sessionId,
          status: err?.response?.status,
          message: err?.message
        })
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          navigate('/', { replace: true })
          return
        }
        if (err?.response?.status === 404) {
          setError('This report is not available yet.')
          return
        }
        setError('Failed to load the report. Please try again.')
      })
    return () => { cancelled = true }
  }, [sessionId, navigate])

  if (error) {
    return (
      <div className="aura-dashboard-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <nav className="nav">
          <div className="nav-row">
            <Link to="/" className="brand"><span className="mark" aria-hidden="true"></span><span>Aura</span></Link>
            <div className="nav-cta">
              <Link to="/my-interviews" className="btn btn-ghost btn-sm">My interviews</Link>
            </div>
          </div>
        </nav>
        <main className="container">
          <div className="page-head">
            <span className="page-eyebrow"><span className="lit">Report</span></span>
            <h1 className="page-h1">Report not available</h1>
          </div>
          <div className="error-banner" role="alert">{error}</div>
          <Link to="/my-interviews" className="btn btn-ghost" style={{ marginTop: 12 }}>
            ← Back to my interviews
          </Link>
        </main>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="aura-dashboard-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <nav className="nav">
          <div className="nav-row">
            <Link to="/" className="brand"><span className="mark" aria-hidden="true"></span><span>Aura</span></Link>
            <div className="nav-cta">
              {user && (
                <span className="user-chip">
                  <span className="avatar" aria-hidden="true">{initials(user.name || user.email)}</span>
                  {user.name || user.email}
                </span>
              )}
            </div>
          </div>
        </nav>
        <main className="container">
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading report…</span>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="aura-dashboard-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      <nav className="nav" aria-label="Primary">
        <div className="nav-row">
          <Link to="/" className="brand" aria-label="Aura home">
            <span className="mark" aria-hidden="true"></span><span>Aura</span>
          </Link>
          <div className="nav-links">
            <Link to="/interview">New interview</Link>
            <Link to="/my-interviews" className="active">My interviews</Link>
          </div>
          <div className="nav-cta">
            {user && (
              <span className="user-chip">
                <span className="avatar" aria-hidden="true">{initials(user.name || user.email)}</span>
                {user.name || user.email}
              </span>
            )}
            <button className="btn btn-ghost btn-sm" onClick={logout}>Sign out</button>
          </div>
        </div>
      </nav>

      <main className="container">
        <Link to="/my-interviews" className="back-link">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          Back to my interviews
        </Link>

        <ReportView
          report={report}
          sessionId={sessionId!}
          onDone={() => navigate('/my-interviews')}
        />
      </main>
    </div>
  )
}
