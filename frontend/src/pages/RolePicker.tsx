import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { setUserRole } from '@/api/client'
import '@/styles/aura-pre.css'

/**
 * Role picker and role switcher.
 *
 * New users (role ``''``) land here from the OAuth callback and from the
 * email/password sign-in. Existing users reach it via the "Switch role" link
 * (``?switch=1``); without that flag they are sent back, so the page cannot be
 * used to bounce a settled user around the app.
 */
export function RolePicker() {
  const { user, setAuth } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const switching = params.get('switch') === '1'
  const [busy, setBusy] = useState<'candidate' | 'recruiter' | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Authenticated users who already picked a role don't belong here — unless
  // they explicitly asked to switch. Redirect via <Navigate> rather than
  // navigate(): calling it during render is unsafe under StrictMode.
  if (user && user.role !== '' && !switching) {
    const returnTo = sessionStorage.getItem('aura_return_to')
    return <Navigate to={returnTo || '/'} replace />
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

  const current = user?.role

  return (
    <div className="aura-pre-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      <main className="container" style={{ maxWidth: 760 }}>
        <span className="eyebrow"><span className="dot" aria-hidden="true"></span>{switching ? 'Switch mode' : 'Welcome to Aura'}</span>
        <h1 className="h1">How will you <em>use Aura?</em></h1>
        <p className="lede">
          {switching
            ? 'Pick the other mode to switch. You can switch back at any time.'
            : 'Pick the mode that fits you. You can switch anytime from the profile menu.'}
        </p>

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
                <button
                  className="btn btn-primary"
                  disabled={busy !== null || current === 'candidate'}
                  onClick={() => choose('candidate')}
                >
                  {busy === 'candidate'
                    ? <><span className="spinner" /> Setting up…</>
                    : current === 'candidate' ? 'Current mode' : "I'm a candidate"}
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
                <button
                  className="btn btn-primary"
                  disabled={busy !== null || current === 'recruiter'}
                  onClick={() => choose('recruiter')}
                >
                  {busy === 'recruiter'
                    ? <><span className="spinner" /> Setting up…</>
                    : current === 'recruiter' ? 'Current mode' : "I'm a recruiter"}
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