import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getAdminSessionDetail, type SessionDetail as SessionDetailData, type TranscriptEntryRead } from '@/api/client'
import { ReportView } from '@/components/interview/ReportView'
import { useAuth } from '@/contexts/AuthContext'
import '@/styles/aura-dashboard.css'

const formatDateTime = (iso: string | null) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const formatDuration = (secs: number | null | undefined) => {
  if (secs == null) return '—'
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

const statusPill = (status: SessionDetailData['status']) => {
  switch (status) {
    case 'completed':   return { cls: 'pill pill-success', text: 'Completed' }
    case 'in_progress': return { cls: 'pill pill-accent',  text: 'In Progress' }
    case 'pending':     return { cls: 'pill pill-muted',   text: 'Pending' }
    default:            return { cls: 'pill pill-muted',   text: status }
  }
}

const initials = (name: string) =>
  name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() || '?'

export function SessionDetail() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { sessionId } = useParams<{ sessionId: string }>()
  const [data, setData] = useState<SessionDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null)
    setError(null)
    getAdminSessionDetail(sessionId)
      .then(d => { if (!cancelled) setData(d) })
      .catch(err => {
        if (cancelled) return
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          navigate('/', { replace: true })
          return
        }
        if (err?.response?.status === 404) {
          setError('Session not found.')
          return
        }
        setError('Failed to load session detail. Please try again.')
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
              <Link to="/admin" className="btn btn-ghost btn-sm">Back to dashboard</Link>
            </div>
          </div>
        </nav>
        <main className="container">
          <div className="page-head">
            <span className="page-eyebrow"><span className="lit">Admin</span>· Session</span>
            <h1 className="page-h1">Session not available</h1>
          </div>
          <div className="error-banner" role="alert">{error}</div>
          <Link to="/admin" className="btn btn-ghost" style={{ marginTop: 12 }}>
            ← Back to admin dashboard
          </Link>
        </main>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="aura-dashboard-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <nav className="nav">
          <div className="nav-row">
            <Link to="/" className="brand"><span className="mark" aria-hidden="true"></span><span>Aura</span></Link>
          </div>
        </nav>
        <main className="container">
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading session…</span>
          </div>
        </main>
      </div>
    )
  }

  // Once the report is available, render the full ReportView on top so admins
  // get the same polished report UI the candidate sees — then layer the
  // transcript and metadata beneath.
  const status = statusPill(data.status)
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
            <Link to="/my-interviews">My interviews</Link>
            <Link to="/admin" className="active">Admin</Link>
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
        <Link to="/admin" className="back-link">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          Back to admin dashboard
        </Link>

        <header className="page-head">
          <span className="page-eyebrow">
            <span className="lit">Admin</span>· {data.candidate_name}
            <span style={{ color: 'var(--muted-2)' }}>· {data.user_email || 'no email'}</span>
          </span>
          <h1 className="page-h1">{data.candidate_name}</h1>
          <div style={{ marginTop: 8, display: 'flex', gap: 10, alignItems: 'center' }}>
            <span className={status.cls}><span className="dot"></span>{status.text}</span>
            {data.report && (
              <span className="muted" style={{ fontSize: 13 }}>
                Score {data.report.overall_score} · {data.report.recommendation}
              </span>
            )}
          </div>
        </header>

        <div className="detail-meta" aria-label="Session metadata">
          <div>
            <div className="meta-label">Candidate</div>
            <div className="meta-value">{data.candidate_name}</div>
          </div>
          <div>
            <div className="meta-label">User</div>
            <div className="meta-value">{data.user_email || '—'}</div>
          </div>
          <div>
            <div className="meta-label">Created</div>
            <div className="meta-value">{formatDateTime(data.created_at)}</div>
          </div>
          <div>
            <div className="meta-label">Completed</div>
            <div className="meta-value">{formatDateTime(data.completed_at)}</div>
          </div>
          <div>
            <div className="meta-label">Duration</div>
            <div className="meta-value">{formatDuration(
              data.completed_at && data.created_at
                ? Math.round((new Date(data.completed_at).getTime() - new Date(data.created_at).getTime()) / 1000)
                : null
            )}</div>
          </div>
        </div>

        {data.report ? (
          <section aria-label="Report" style={{ marginTop: 8 }}>
            <h2 className="section-title">Report</h2>
            <ReportView
              report={data.report}
              sessionId={data.session_id}
              onDone={() => navigate('/admin')}
            />
          </section>
        ) : (
          <div className="card">
            <div className="empty">
              <h3>No report yet</h3>
              <p>This session is {data.status}. A report will be available once the interview is completed.</p>
            </div>
          </div>
        )}

        {data.transcript && data.transcript.length > 0 ? (
          <section aria-label="Transcript">
            <h2 className="section-title">Transcript</h2>
            <div className="card">
              <div className="transcript" role="log" aria-label="Interview transcript">
                {data.transcript.map((entry: TranscriptEntryRead, i: number) => {
                  const isAssistant = entry.speaker.toLowerCase().includes('aura') ||
                    entry.speaker.toLowerCase().includes('agent') ||
                    entry.speaker.toLowerCase().includes('assistant')
                  return (
                    <div key={i} className={`transcript-line ${isAssistant ? 'assistant' : ''}`}>
                      <span className="who">{entry.speaker}</span>
                      <span className="text">{entry.text}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </section>
        ) : data.status === 'completed' ? (
          <section aria-label="Transcript">
            <h2 className="section-title">Transcript</h2>
            <div className="card">
              <div className="empty">
                <p>No transcript was captured for this session.</p>
              </div>
            </div>
          </section>
        ) : null}
      </main>
    </div>
  )
}
