import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listAdminSessions, type SessionSummary } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { recPill, statusPill, formatDate, initials } from '@/lib/dashboard-utils'
import '@/styles/aura-dashboard.css'

type StatusFilter = 'all' | 'pending' | 'in_progress' | 'completed'
type SortKey = 'created_at' | 'candidate_name' | 'overall_score' | 'status'

export function AdminDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  useEffect(() => {
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSessions(null)
    setError(null)
    listAdminSessions()
      .then(data => { if (!cancelled) setSessions(data) })
      .catch(err => {
        if (cancelled) return
        console.error('Failed to load admin sessions:', {
          status: err?.response?.status,
          message: err?.message,
          url: err?.config?.url
        })
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          navigate('/', { replace: true })
          return
        }
        setError('Failed to load sessions. Please try again.')
      })
    return () => { cancelled = true }
  }, [navigate])

  const filteredAndSorted = useMemo(() => {
    if (!sessions) return []
    let list = sessions.slice()
    if (statusFilter !== 'all') {
      list = list.filter(s => s.status === statusFilter)
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(s => s.candidate_name.toLowerCase().includes(q))
    }
    list.sort((a, b) => {
      let av: number | string
      let bv: number | string
      switch (sortKey) {
        case 'candidate_name':
          av = a.candidate_name.toLowerCase()
          bv = b.candidate_name.toLowerCase()
          break
        case 'overall_score':
          av = a.overall_score ?? -1
          bv = b.overall_score ?? -1
          break
        case 'status':
          av = a.status
          bv = b.status
          break
        case 'created_at':
        default:
          av = new Date(a.created_at).getTime()
          bv = new Date(b.created_at).getTime()
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return list
  }, [sessions, statusFilter, search, sortKey, sortDir])

  const stats = useMemo(() => {
    const list = sessions ?? []
    const total = list.length
    const completed = list.filter(s => s.status === 'completed')
    const completionRate = total === 0 ? 0 : Math.round((completed.length / total) * 100)
    const scoredSessions = completed.filter(s => s.overall_score !== null)
    const avgScore = scoredSessions.length === 0
      ? null
      : Math.round(scoredSessions.reduce((sum, s) => sum + (s.overall_score ?? 0), 0) / scoredSessions.length)
    return { total, completed: completed.length, completionRate, avgScore }
  }, [sessions])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(key === 'created_at' ? 'desc' : 'asc')
    }
  }

  const sortIndicator = (key: SortKey) => {
    if (sortKey !== key) return null
    return <span className="sort-ind">{sortDir === 'asc' ? '▲' : '▼'}</span>
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
        <header className="page-head">
          <span className="page-eyebrow"><span className="lit">Admin</span>· Dashboard</span>
          <h1 className="page-h1">All <em>interviews</em></h1>
          <p className="lede">Every session across all candidates, with scores, recommendations, and direct links to full reports.</p>
        </header>

        {error && <div className="error-banner" role="alert">{error}</div>}

        {sessions === null && !error ? (
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading sessions…</span>
          </div>
        ) : sessions && sessions.length === 0 ? (
          <div className="card">
            <div className="empty">
              <h3>No sessions yet</h3>
              <p>Once candidates run their first interview, you'll see them here.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="stats-bar" aria-label="Dashboard statistics">
              <div className="stat-card">
                <div className="stat-label">Total sessions</div>
                <div className="stat-value">{stats.total}</div>
                <div className="stat-foot">All time</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Completed</div>
                <div className="stat-value">{stats.completed}</div>
                <div className="stat-foot">{stats.completionRate}% completion rate</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Average score</div>
                <div className="stat-value">{stats.avgScore ?? '—'}</div>
                <div className="stat-foot">Across completed sessions</div>
              </div>
            </div>

            <div className="filter-bar" role="search">
              <div className="search">
                <input
                  type="search"
                  placeholder="Search by candidate name…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  aria-label="Search sessions"
                />
              </div>
              <div className="seg" role="tablist" aria-label="Filter by status">
                {(['all', 'completed', 'in_progress', 'pending'] as StatusFilter[]).map(s => (
                  <button
                    key={s}
                    role="tab"
                    aria-selected={statusFilter === s}
                    className={statusFilter === s ? 'active' : ''}
                    onClick={() => setStatusFilter(s)}
                  >
                    {s === 'all' ? 'All' : s === 'in_progress' ? 'In progress' : s.charAt(0).toUpperCase() + s.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            <div className="card">
              <table className="table" role="table">
                <thead>
                  <tr>
                    <th scope="col" className="sortable" onClick={() => toggleSort('candidate_name')}>
                      Candidate {sortIndicator('candidate_name')}
                    </th>
                    <th scope="col" className="sortable" onClick={() => toggleSort('overall_score')}>
                      Score {sortIndicator('overall_score')}
                    </th>
                    <th scope="col">Recommendation</th>
                    <th scope="col" className="sortable" onClick={() => toggleSort('status')}>
                      Status {sortIndicator('status')}
                    </th>
                    <th scope="col" className="sortable" onClick={() => toggleSort('created_at')}>
                      Date {sortIndicator('created_at')}
                    </th>
                    <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAndSorted.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ textAlign: 'center', color: 'var(--muted-2)', padding: '40px 18px' }}>
                        No sessions match your filters.
                      </td>
                    </tr>
                  ) : filteredAndSorted.map(s => {
                    const rec = recPill(s.recommendation)
                    const status = statusPill(s.status)
                    return (
                      <tr key={s.session_id} onClick={() => navigate(`/admin/session/${s.session_id}`)}>
                        <td>{s.candidate_name}</td>
                        <td className="num">{s.overall_score ?? <span className="muted">—</span>}</td>
                        <td><span className={rec.cls}><span className="dot"></span>{rec.text}</span></td>
                        <td><span className={status.cls}><span className="dot"></span>{status.text}</span></td>
                        <td className="num">{formatDate(s.created_at)}</td>
                        <td style={{ textAlign: 'right' }}>
                          <Link
                            to={`/admin/session/${s.session_id}`}
                            className="btn btn-ghost btn-sm"
                            onClick={e => e.stopPropagation()}
                          >
                            View
                          </Link>
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
