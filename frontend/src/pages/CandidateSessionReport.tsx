import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { downloadArtifact, getMySessionDetail, type SessionDetail, type TranscriptEntryRead } from '@/api/client'
import { ReportView } from '@/components/interview/ReportView'
import { AppHeader } from '@/components/layout/AppHeader'
import '@/styles/aura-dashboard.css'

export function CandidateSessionReport() {
  const navigate = useNavigate()
  const { sessionId } = useParams<{ sessionId: string }>()
  const [data, setData] = useState<SessionDetail | null>(null)
  const [tab, setTab] = useState<'report' | 'transcript'>('report')
  const [error, setError] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null)
    setError(null)
    getMySessionDetail(sessionId)
      .then(r => { if (!cancelled) setData(r) })
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
        <AppHeader links={false} />
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

  if (!data) {
    return (
      <div className="aura-dashboard-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <AppHeader links={false} />
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

      <AppHeader active="my-interviews" />

      <main className="container">
        <Link to="/my-interviews" className="back-link">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          Back to my interviews
        </Link>

        <div className="filter-bar" role="tablist" aria-label="Interview artifacts" style={{ marginBottom: 20 }}>
          <button className={`btn ${tab === 'report' ? 'btn-primary' : 'btn-ghost'}`} role="tab" aria-selected={tab === 'report'} onClick={() => setTab('report')}>Report</button>
          <button className={`btn ${tab === 'transcript' ? 'btn-primary' : 'btn-ghost'}`} role="tab" aria-selected={tab === 'transcript'} onClick={() => setTab('transcript')}>Transcript</button>
          <button className="btn btn-ghost" style={{ marginLeft: 'auto' }} disabled={!data.report} onClick={() => handleDownload('pdf')}>Download PDF</button>
          <button className="btn btn-ghost" disabled={!data.transcript?.length} onClick={() => handleDownload('transcript')}>Download transcript</button>
        </div>
        {downloadError && <div className="error-banner" role="alert" style={{ marginBottom: 16 }}>{downloadError}</div>}

        {tab === 'report' && data.report ? (
          <ReportView report={data.report} sessionId={sessionId!} onDone={() => navigate('/my-interviews')} />
        ) : tab === 'report' ? (
          <div className="card"><div className="empty"><h3>Report not ready</h3><p>The report will appear once the interview is complete.</p></div></div>
        ) : data.transcript && data.transcript.length > 0 ? (
          <div className="card">
            <div className="transcript" role="log" aria-label="Interview transcript">
              {data.transcript.map((entry: TranscriptEntryRead, index: number) => (
                <div key={index} className={`transcript-line ${entry.speaker === 'Interviewer' ? 'assistant' : ''}`}>
                  <span className="who">{entry.speaker} · {formatTimestamp(entry.timestamp_s)}</span>
                  <span className="text">{entry.text}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="card"><div className="empty"><h3>No transcript available</h3><p>The transcript will appear after the interview concludes.</p></div></div>
        )}
      </main>
    </div>
  )

  async function handleDownload(fileType: 'pdf' | 'transcript') {
    if (!sessionId) return
    setDownloadError(null)
    try {
      await downloadArtifact(sessionId, fileType)
    } catch {
      setDownloadError(`Could not download the ${fileType === 'pdf' ? 'PDF report' : 'transcript'}. Please try again.`)
    }
  }
}

function formatTimestamp(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.floor(seconds % 60)
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}
