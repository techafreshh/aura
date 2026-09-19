import { Link } from 'react-router-dom'
import '@/styles/aura-dashboard.css'

interface ErrorFallbackProps {
  error?: unknown
  resetError?: () => void
}

/** Branded full-page fallback for unhandled render errors (Sentry ErrorBoundary). */
export function ErrorFallback({ error, resetError }: ErrorFallbackProps) {
  const message =
    error instanceof Error && error.message ? error.message : 'An unexpected error occurred.'

  return (
    <div className="aura-dashboard-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      <nav className="nav" aria-label="Primary">
        <div className="nav-row">
          <Link to="/" className="brand" aria-label="Aura home">
            <span className="mark" aria-hidden="true"></span><span>Aura</span>
          </Link>
        </div>
      </nav>

      <main className="container" style={{ paddingTop: 96, paddingBottom: 96 }}>
        <div style={{ maxWidth: 560, margin: '0 auto', textAlign: 'center' }}>
          <span
            className="page-eyebrow"
            style={{ justifyContent: 'center', display: 'flex' }}
          >
            <span className="lit">Something broke</span>· Unexpected error
          </span>
          <h1 className="page-h1" style={{ margin: '12px 0 8px' }}>
            This page hit an <em>error.</em>
          </h1>
          <p className="lede" style={{ marginBottom: 32 }}>
            {message} The issue has been logged. Try reloading the page — if it
            keeps happening, head back home and pick up where you left off.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                if (resetError) {
                  resetError()
                } else {
                  window.location.reload()
                }
              }}
            >
              Try again
            </button>
            <Link to="/" className="btn btn-ghost">
              Back to home
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}
