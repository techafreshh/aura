import { Link, useNavigate } from 'react-router-dom'
import { useAuth, type Mode } from '@/contexts/AuthContext'
import { initials } from '@/lib/dashboard-utils'

export type HeaderLink =
  | 'new-interview'
  | 'my-interviews'
  | 'recruiter'
  | 'admin'
  | 'profile'

interface AppHeaderProps {
  /** Link rendered as active (bottom accent underline). */
  active?: HeaderLink
  /** Hide the link row (pages with their own in-content navigation). */
  links?: false
}

/**
 * Shared dashboard header: brand, mode-aware links, the candidate/recruiter
 * mode switcher, and the user chip. Every dashboard-style page used to copy
 * this markup; mode switching (Upwork-style) is client-side — setMode flips
 * localStorage + context state and routes to that mode's home, no API call.
 */
export function AppHeader({ active, links = undefined }: AppHeaderProps) {
  const { user, mode, setMode, logout } = useAuth()
  const navigate = useNavigate()

  const isAdmin = user?.role === 'admin'
  // Dual roles: admin, or anyone holding the one-way is_recruiter grant.
  const canRecruit = isAdmin || user?.role === 'recruiter' || !!user?.is_recruiter

  const switchTo = (next: Mode) => {
    if (next === mode) return
    setMode(next)
    navigate(next === 'recruiter' ? '/recruiter' : '/interview')
  }

  return (
    <nav className="nav" aria-label="Primary">
      <div className="nav-row">
        <Link to="/" className="brand" aria-label="Aura home">
          <span className="mark" aria-hidden="true"></span><span>Aura</span>
        </Link>
        {links !== false && (
          <div className="nav-links">
            <Link to="/interview" className={active === 'new-interview' ? 'active' : undefined}>New interview</Link>
            <Link to="/my-interviews" className={active === 'my-interviews' ? 'active' : undefined}>My interviews</Link>
            {canRecruit && (
              <Link to="/recruiter" className={active === 'recruiter' ? 'active' : undefined}>Recruiter</Link>
            )}
            {isAdmin && (
              <Link to="/admin" className={active === 'admin' ? 'active' : undefined}>Admin</Link>
            )}
            <Link
              to={mode === 'recruiter' ? '/profile/recruiter' : '/profile/candidate'}
              className={active === 'profile' ? 'active' : undefined}
            >
              Profile
            </Link>
          </div>
        )}
        <div className="nav-cta">
          {canRecruit && (
            <div className="nav-mode" role="tablist" aria-label="Active role">
              <button
                role="tab"
                aria-selected={mode === 'candidate'}
                className={mode === 'candidate' ? 'active' : undefined}
                onClick={() => switchTo('candidate')}
              >
                Candidate
              </button>
              <button
                role="tab"
                aria-selected={mode === 'recruiter'}
                className={mode === 'recruiter' ? 'active' : undefined}
                onClick={() => switchTo('recruiter')}
              >
                Recruiter
              </button>
            </div>
          )}
          {user?.role === '' && <Link to="/choose-role">Choose role</Link>}
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
  )
}
