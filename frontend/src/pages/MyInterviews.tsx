import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listMySessions, type SessionSummary } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import '@/styles/aura-dashboard.css'

const recPill = (rec: SessionSummary['recommendation']) => {
  switch (rec) {
    case 'Strong Hire': return { cls: 'pill pill-success', text: 'Strong Hire' }
    case 'Hire':        return { cls: 'pill pill-success', text: 'Hire' }
    case 'Hold':        return { cls: 'pill pill-warn',    text: 'Hold' }
    case 'No Hire':     return { cls: 'pill pill-danger',  text: 'No Hire' }
    default:            return { cls: 'pill pill-muted',   text: '—' }
  }
}

const statusPill = (status: SessionSummary['status']) => {
  switch (status) {
    case 'completed':   return { cls: 'pill pill-success', text: 'Completed' }
    case 'in_progress': return { cls: 'pill pill-accent',  text: 'In Progress' }
    case 'pending':     return { cls: 'pill pill-muted',   text: 'Pending' }
    default:            return { cls: 'pill pill-muted',   text: status }
  }
}

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })

const initials = (name: string) =>
  name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() || '?'

export function MyInterviews() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSessions(null)
    setError(null)
    listMySessions()
      .then(data => { if (!cancelled) setSessions(data) })
      .catch(err => {
        if (cancelled) return
        if (err?.response?.status === 401) {
          navigate('/', { replace: true })
          return
        }
        setError('Failed to load your interviews. Please try again.')
      })
    return () => { cancelled = true }
  }, [navigate])

  const filtered = (sessions ?? []).filter(s =>
    s.candidate_name.toLowerCase().includes(search.toLowerCase())
  )

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
            {user?.role === 'admin' && <Link to="/admin">Admin dashboard</Link>}
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
        <header className="page-head">
          <span className="page-eyebrow"><span className="lit">Your history</span>· Sessions</span>
          <h1 className="page-h1">My <em>interviews</em></h1>
          <p className="lede">Review your past sessions, scores, and reports. Start a new interview whenever you're ready.</p>
          <div style={{ marginTop: 18 }}>
            <Link to="/interview" className="btn btn-primary">
              Start a new interview
              <svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </Link>
          </div>
        </header>

        {error && <div className="error-banner" role="alert">{error}</div>}

        {sessions === null && !error ? (
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading your interviews…</span>
          </div>
        ) : sessions && sessions.length === 0 ? (
          <div className="card">
            <div className="empty">
              <h3>No interviews yet</h3>
              <p>Once you complete an interview, it'll show up here.</p>
              <div className="empty-cta">
                <Link to="/interview" className="btn btn-primary">Start your first interview</Link>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="filter-bar" role="search">
              <div className="search">
                <input
                  type="search"
                  placeholder="Search by candidate name…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  aria-label="Search interviews"
                />
              </div>
            </div>

            <div className="card">
              <table className="table" role="table">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Score</th>
                    <th scope="col">Recommendation</th>
                    <th scope="col">Status</th>
                    <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ textAlign: 'center', color: 'var(--muted-2)', padding: '40px 18px' }}>
                        No interviews match "{search}".
                      </td>
                    </tr>
                  ) : filtered.map(s => {
                    const rec = recPill(s.recommendation)
                    const status = statusPill(s.status)
                    const canView = s.status === 'completed'
                    return (
                      <tr key={s.session_id} onClick={() => canView && navigate(`/my-interviews/${s.session_id}`)}>
                        <td className="num">{formatDate(s.created_at)}</td>
                        <td className="num">{s.overall_score ?? <span className="muted">—</span>}</td>
                        <td><span className={rec.cls}><span className="dot"></span>{rec.text}</span></td>
                        <td><span className={status.cls}><span className="dot"></span>{status.text}</span></td>
                        <td style={{ textAlign: 'right' }}>
                          {canView ? (
                            <Link
                              to={`/my-interviews/${s.session_id}`}
                              className="btn btn-ghost btn-sm"
                              onClick={e => e.stopPropagation()}
                            >
                              View
                            </Link>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
