import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { setUserRole } from '@/api/client'
import { Link } from 'react-router-dom'
import '@/styles/aura-pre.css'

export function RolePicker() {
  const { user, setAuth } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<'candidate' | 'recruiter' | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Authenticated users who already picked a role don't belong here
  if (user && user.role !== '') {
    const returnTo = sessionStorage.getItem('aura_return_to')
    if (returnTo) {
      sessionStorage.removeItem('aura_return_to')
      navigate(returnTo, { replace: true })
    } else {
      navigate('/', { replace: true })
    }
    return null
  }

  const choose = async (role: 'candidate' | 'recruiter') => {
    setBusy(role)
    setError(null)
    try {
      const data = await setUserRole(role)
      setAuth(data.token, { ...data.user, role: data.user.role as 'candidate' | 'recruiter', avatar_url: data.user.avatar_url ?? undefined })
      const returnTo = sessionStorage.getItem('aura_return_to')
      sessionStorage.removeItem('aura_return_to')
      navigate(returnTo || (role === 'recruiter' ? '/recruiter' : '/interview'), { replace: true })
    } catch {
      setError('Could not save your choice. Please try again.')
      setBusy(null)
    }
  }

  return (
    <div className="aura-pre-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      <main className="container" style={{ maxWidth: 760 }}>
        <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Welcome to Aura</span>
        <h1 className="h1">How will you <em>use Aura?</em></h1>
        <p className="lede">Pick the mode that fits you. You can switch anytime from the profile menu.</p>

        {error && (
          <div className="error-banner" role="alert" style={{ marginTop: 16 }}>{error}</div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 24 }}>
          <article className="card" style={{ margin: 0 }}>
            <div className="card-body">
              <span className="eyebrow"><span className="dot" aria-hidden="true"></span>For myself</span>
              <h2 style={{ margin: '8px 0 6px', fontSize: 22 }}>Candidate</h2>
              <p style={{ opacity: 0.75, fontSize: 14, lineHeight: 1.6 }}>
                Practice interviews with an AI interviewer. Upload your resume, optionally add a
                job description, and get a structured report with scores and feedback.
              </p>
              <div className="btn-row" style={{ marginTop: 18 }}>
                <button className="btn btn-primary" disabled={busy !== null} onClick={() => choose('candidate')}>
                  {busy === 'candidate' ? <><span className="spinner" /> Setting up…</> : "I'm a candidate"}
                </button>
              </div>
            </div>
          </article>

          <article className="card" style={{ margin: 0 }}>
            <div className="card-body">
              <span className="eyebrow"><span className="dot" aria-hidden="true"></span>For my team</span>
              <h2 style={{ margin: '8px 0 6px', fontSize: 22 }}>Recruiter</h2>
              <p style={{ opacity: 0.75, fontSize: 14, lineHeight: 1.6 }}>
                Create interviews with your own questions, send candidates a private link, and
                review the PDF report and audio recording when they're done.
              </p>
              <div className="btn-row" style={{ marginTop: 18 }}>
                <button className="btn btn-primary" disabled={busy !== null} onClick={() => choose('recruiter')}>
                  {busy === 'recruiter' ? <><span className="spinner" /> Setting up…</> : "I'm a recruiter"}
                </button>
              </div>
            </div>
          </article>
        </div>

        <p style={{ marginTop: 20, fontSize: 13, opacity: 0.6 }}>
          Signed in as {user?.email} · <Link to="/" style={{ color: 'inherit' }}>Back to home</Link>
        </p>
      </main>
    </div>
  )
}
