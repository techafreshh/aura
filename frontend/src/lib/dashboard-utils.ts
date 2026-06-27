/**
 * Shared utility functions for dashboard pages.
 *
 * Extracted from AdminDashboard, MyInterviews, SessionDetail, and
 * CandidateSessionReport to avoid code duplication.
 */

export type Recommendation = 'Hire' | 'No Hire' | 'Strong Hire' | 'Hold' | null;
export type SessionStatus = 'pending' | 'in_progress' | 'completed';

/** Return pill CSS class and display text for a hiring recommendation. */
export const recPill = (rec: Recommendation) => {
  switch (rec) {
    case 'Strong Hire': return { cls: 'pill pill-success', text: 'Strong Hire' }
    case 'Hire':        return { cls: 'pill pill-success', text: 'Hire' }
    case 'Hold':        return { cls: 'pill pill-warn',    text: 'Hold' }
    case 'No Hire':     return { cls: 'pill pill-danger',  text: 'No Hire' }
    default:            return { cls: 'pill pill-muted',   text: '—' }
  }
}

/** Return pill CSS class and display text for a session status. */
export const statusPill = (status: SessionStatus) => {
  switch (status) {
    case 'completed':   return { cls: 'pill pill-success', text: 'Completed' }
    case 'in_progress': return { cls: 'pill pill-accent',  text: 'In Progress' }
    case 'pending':     return { cls: 'pill pill-muted',   text: 'Pending' }
    default:            return { cls: 'pill pill-muted',   text: status }
  }
}

/** Format an ISO date string to a human-readable date. */
export const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })

/** Format an ISO datetime string, returning '—' for null. */
export const formatDateTime = (iso: string | null) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}

/** Format seconds into a human-readable duration string. */
export const formatDuration = (secs: number | null | undefined) => {
  if (secs == null) return '—'
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

/** Extract up to two initials from a name, or '?' for empty input. */
export const initials = (name: string) =>
  name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() || '?'
