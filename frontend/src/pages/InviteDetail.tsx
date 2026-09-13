import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import axios from 'axios'
import { getRecruiterInvite, downloadFile, type InviteDetail as InviteDetailData } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { statusPill, formatDateTime, initials } from '@/lib/dashboard-utils'
import { ReportView } from '@/components/interview/ReportView'
import '@/styles/aura-dashboard.css'

export function InviteDetail() {
  const { inviteId } = useParams<{ inviteId: string }>()
  const { user, logout } = useAuth()
  const [invite, setInvite] = useState<InviteDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)

  useEffect(() => {
    if (!inviteId) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setInvite(null)
    setError(null)
    getRecruiterInvite(inviteId)
      .then(data => { if (!cancelled) setInvite(data) })
      .catch(err => {
        if (cancelled) return
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          setError("You don't have access to this interview.")
        } else if (err?.response?.status === 404) {
          setError('Interview not found.')
        } else {
          setError('Failed to load the interview.')
        }
      })
    return () => { cancelled = true }
  }, [inviteId])

  // Load the recording as an authenticated blob so it can be played inline
  useEffect(() => {
    if (!invite?.session_id || invite.status !== 'completed') return
    const url = URL.createObjectURL.bind(URL)
    let objectUrl: string | null = null
    axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/download/${invite.session_id}/audio`, {
      responseType: 'blob',
      headers: { Authorization: `Bearer ${localStorage.getItem('aura_token')}` },
    })
      .then(res => {
        objectUrl = url(res.data as Blob)
        setAudioUrl(objectUrl)
      })
      .catch(() => setAudioUrl(null))
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [invite])

  const download = async (fileType: 'pdf' | 'audio') => {
    if (!invite?.session_id) return
    setDownloading(fileType)
    try {
      if (fileType === 'pdf') {
        await downloadFile(`/download/${invite.session_id}/pdf`, `interview-report-${invite.candidate_name || 'candidate'}.pdf`)
      } else {
        await downloadFile(`/download/${invite.session_id}/audio`, `interview-recording-${invite.candidate_name || 'candidate'}.webm`)
      }
    } catch {
      setError('Download failed. The file may not be ready.')
    } finally {
      setDownloading(null)
    }
  }

  if (error) {
    return (
      <div className="aura-dashboard-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <main className="container" style={{ paddingTop: 60 }}>
          <div className="card">
            <div className="empty">
              <h3>{error}</h3>
              <Link to="/recruiter" className="btn btn-primary" style={{ marginTop: 12 }}>Back to dashboard</Link>
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (!invite) {
    return (
      <div className="aura-dashboard-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <main className="container" style={{ paddingTop: 60 }}>
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading interview…</span>
          </div>
        </main>
      </div>
    )
  }

  // Completed interviews get the full report view
  if (invite.status === 'completed' && invite.report) {
    return (
      <ReportView
        report={invite.report}
        sessionId={invite.session_id || ''}
        onDone={() => window.history.back()}
        recruiterActions={
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {audioUrl && <audio controls src={audioUrl} style={{ height: 36 }} aria-label="Interview recording" />}
            <button className="btn btn-ghost btn-sm" onClick={() => download('audio')} disabled={downloading !== null}>
              {downloading === 'audio' ? 'Preparing…' : 'Download audio'}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => download('pdf')} disabled={downloading !== null}>
              {downloading === 'pdf' ? 'Preparing…' : 'Download PDF'}
            </button>
          </div>
        }
      />
    )
  }

  const status = statusPill(invite.status === 'cancelled' ? 'pending' : invite.status)

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
            <Link to="/recruiter">Recruiter</Link>
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

      <main className="container" style={{ maxWidth: 860 }}>
        <header className="page-head">
          <span className="page-eyebrow"><span className="lit">Interview</span>· Details</span>
          <h1 className="page-h1">{invite.title}</h1>
          <p className="lede">
            <span className={invite.status === 'cancelled' ? 'pill pill-muted' : status.cls}>
              <span className="dot"></span>{invite.status === 'cancelled' ? 'Cancelled' : status.text}
            </span>
            <span style={{ marginLeft: 12, opacity: 0.7 }}>Created {formatDateTime(invite.created_at)}</span>
          </p>
        </header>

        {invite.candidate_name && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-body">
              <div className="preview-head">
                <div className="avatar">{initials(invite.candidate_name)}</div>
                <div>
                  <h2 className="name" style={{ margin: 0, fontSize: 18 }}>{invite.candidate_name}</h2>
                  <div className="sub">Started {formatDateTime(invite.created_at)}</div>
                </div>
              </div>
            </div>
          </div>
        )}

        <article className="card">
          <div className="card-body">
            {invite.context && (
              <>
                <div className="label-row">Context shared with the interviewer</div>
                <p style={{ margin: '8px 0 0', opacity: 0.8, fontSize: 14, lineHeight: 1.6 }}>{invite.context}</p>
                <div className="hr" />
              </>
            )}
            <div className="label-row">Questions</div>
            <ol style={{ margin: '10px 0 0', paddingLeft: 20, lineHeight: 2 }}>
              {invite.questions.map((q, i) => <li key={i}>{q}</li>)}
            </ol>
            {invite.status === 'completed' && (
              <>
                <div className="hr" />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary btn-sm" onClick={() => download('audio')} disabled={downloading !== null}>
                    {downloading === 'audio' ? 'Preparing…' : 'Download audio'}
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => download('pdf')} disabled={downloading !== null}>
                    {downloading === 'pdf' ? 'Preparing…' : 'Download PDF'}
                  </button>
                </div>
                {!audioUrl && (
                  <p style={{ marginTop: 10, fontSize: 12, opacity: 0.55 }}>
                    No recording available — the candidate may have closed the tab before it could upload.
                  </p>
                )}
              </>
            )}
          </div>
        </article>

        <div className="btn-row" style={{ marginTop: 18 }}>
          <Link to="/recruiter" className="btn btn-ghost">Back to dashboard</Link>
        </div>
      </main>
    </div>
  )
}
