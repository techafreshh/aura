import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listRecruiterInvites, cancelInvite, type InviteOut } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { recPill, statusPill, formatDate, initials } from '@/lib/dashboard-utils'
import '@/styles/aura-dashboard.css'

export function RecruiterDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [data, setData] = useState<{ invites: InviteOut[]; quota_used: number; quota_limit: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copiedToken, setCopiedToken] = useState<string | null>(null)

  const load = () => {
    setData(null)
    setError(null)
    listRecruiterInvites()
      .then(setData)
      .catch(err => {
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          navigate('/', { replace: true })
          return
        }
        setError('Failed to load your interviews. Please try again.')
      })
  }

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const inviteLink = (token: string) => `${window.location.origin}/invite/${token}`

  const copyLink = async (token: string) => {
    try {
      await navigator.clipboard.writeText(inviteLink(token))
      setCopiedToken(token)
      setTimeout(() => setCopiedToken(null), 2000)
    } catch {
      window.prompt('Copy this link:', inviteLink(token))
    }
  }

  const cancel = async (invite: InviteOut) => {
    if (!window.confirm(`Cancel "${invite.title}"? Its link will stop working.`)) return
    try {
      await cancelInvite(invite.invite_id)
      load()
    } catch {
      setError('Could not cancel the invite.')
    }
  }

  const invites = data?.invites ?? []
  const pending = invites.filter(i => i.status === 'pending').length
  const completed = invites.filter(i => i.status === 'completed').length
  const quota = data ? `${data.quota_used} / ${data.quota_limit}` : '—'

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
            <Link to="/recruiter" className="active">Recruiter</Link>
            <Link to="/my-interviews">My interviews</Link>
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
          <span className="page-eyebrow"><span className="lit">Recruiter</span>· Interviews</span>
          <h1 className="page-h1">Your <em>interviews</em></h1>
          <p className="lede">Create interviews with your own questions, send candidates a private link, and review their reports and recordings.</p>
          <div style={{ marginTop: 18 }}>
            <Link to="/recruiter/new" className="btn btn-primary">
              New interview
              <svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </Link>
          </div>
        </header>

        {error && <div className="error-banner" role="alert">{error}</div>}

        {data === null && !error ? (
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading your interviews…</span>
          </div>
        ) : (
          <>
            <div className="stats-bar" aria-label="Recruiter statistics">
              <div className="stat-card">
                <div className="stat-label">Monthly usage</div>
                <div className="stat-value">{quota}</div>
                <div className="stat-foot">Interviews started this month</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Awaiting candidates</div>
                <div className="stat-value">{pending}</div>
                <div className="stat-foot">Pending invites</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Completed</div>
                <div className="stat-value">{completed}</div>
                <div className="stat-foot">Reports ready to review</div>
              </div>
            </div>

            {invites.length === 0 ? (
              <div className="card">
                <div className="empty">
                  <h3>No interviews yet</h3>
                  <p>Create your first interview with 2–5 questions and send the link to a candidate.</p>
                  <div className="empty-cta">
                    <Link to="/recruiter/new" className="btn btn-primary">Create an interview</Link>
                  </div>
                </div>
              </div>
            ) : (
              <div className="card">
                <table className="table" role="table">
                  <thead>
                    <tr>
                      <th scope="col">Interview</th>
                      <th scope="col">Candidate</th>
                      <th scope="col">Score</th>
                      <th scope="col">Status</th>
                      <th scope="col">Created</th>
                      <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invites.map(inv => {
                      const rec = recPill(inv.recommendation)
                      const status = statusPill(inv.status === 'cancelled' ? 'pending' : inv.status)
                      const statusLabel = inv.status === 'cancelled' ? 'Cancelled' : status.text
                      return (
                        <tr key={inv.invite_id}>
                          <td style={{ fontWeight: 600 }}>{inv.title}</td>
                          <td>{inv.candidate_name ?? <span className="muted">—</span>}</td>
                          <td className="num">
                            {inv.overall_score ?? <span className="muted">—</span>}
                            {inv.recommendation && (
                              <span className={rec.cls} style={{ marginLeft: 8 }}><span className="dot"></span>{rec.text}</span>
                            )}
                          </td>
                          <td>
                            <span className={inv.status === 'cancelled' ? 'pill pill-muted' : status.cls}>
                              <span className="dot"></span>{statusLabel}
                            </span>
                          </td>
                          <td className="num">{formatDate(inv.created_at)}</td>
                          <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                            {inv.status === 'pending' && (
                              <>
                                <button className="btn btn-ghost btn-sm" onClick={() => copyLink(inv.token)}>
                                  {copiedToken === inv.token ? 'Copied!' : 'Copy link'}
                                </button>
                                <button className="btn btn-ghost btn-sm" onClick={() => cancel(inv)}>Cancel</button>
                              </>
                            )}
                            {inv.status !== 'pending' && inv.invite_id && (
                              <Link to={`/recruiter/invites/${inv.invite_id}`} className="btn btn-ghost btn-sm">
                                {inv.status === 'completed' ? 'View report' : 'Details'}
                              </Link>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
