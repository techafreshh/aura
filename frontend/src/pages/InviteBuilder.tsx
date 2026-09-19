import { useState } from 'react'
import { Link } from 'react-router-dom'
import { createInvite, type InviteOut } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { initials, formatDateTime } from '@/lib/dashboard-utils'
import { Toaster } from '@/components/ui/toaster'
import { useToast } from '@/hooks/use-toast'
import axios from 'axios'
import '@/styles/aura-pre.css'

const MIN_QUESTIONS = 2
const MAX_QUESTIONS = 5

// Link-lifetime choices, in hours. 24h is the product default; the API
// accepts 1–720 (30 days) if a custom value is ever wanted.
const EXPIRY_OPTIONS = [
  { hours: 4, label: '4 hours' },
  { hours: 24, label: '24 hours' },
  { hours: 72, label: '3 days' },
  { hours: 168, label: '7 days' },
]
const DEFAULT_EXPIRY_HOURS = 24

export function InviteBuilder() {
  const { user, logout } = useAuth()
  const { toast } = useToast()
  const [title, setTitle] = useState('')
  const [context, setContext] = useState('')
  const [questions, setQuestions] = useState<string[]>(['', ''])
  const [expiresInHours, setExpiresInHours] = useState<number>(DEFAULT_EXPIRY_HOURS)
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<InviteOut | null>(null)
  const [copied, setCopied] = useState(false)

  const trimmed = questions.map(q => q.trim())
  const valid =
    title.trim().length > 0 &&
    trimmed.every(q => q.length > 0) &&
    trimmed.length >= MIN_QUESTIONS

  const setQuestion = (idx: number, value: string) => {
    setQuestions(qs => qs.map((q, i) => (i === idx ? value : q)))
  }

  const addQuestion = () => {
    if (questions.length < MAX_QUESTIONS) setQuestions(qs => [...qs, ''])
  }

  const removeQuestion = (idx: number) => {
    if (questions.length > MIN_QUESTIONS) setQuestions(qs => qs.filter((_, i) => i !== idx))
  }

  const submit = async () => {
    setCreating(true)
    try {
      const invite = await createInvite({
        title: title.trim(),
        context: context.trim() || undefined,
        questions: trimmed,
        expires_in_hours: expiresInHours,
      })
      setCreated(invite)
    } catch (error) {
      const detail = axios.isAxiosError(error)
        ? (error.response?.data?.detail as string | undefined) ?? 'Could not create the interview.'
        : 'Could not create the interview.'
      toast({ title: 'Creation failed', description: detail, variant: 'destructive' })
    } finally {
      setCreating(false)
    }
  }

  const inviteLink = created ? `${window.location.origin}/invite/${created.token}` : ''

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(inviteLink)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      window.prompt('Copy this link:', inviteLink)
    }
  }

  if (created) {
    return (
      <div className="aura-pre-page">
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
          </div>
        </nav>

        <main className="container" style={{ maxWidth: 760 }}>
          <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Interview created</span>
          <h1 className="h1">Send the <em>private link.</em></h1>
          <p className="lede">
            Only the first candidate who opens this link and signs in can take the interview.
            The report and audio recording will appear in your dashboard when they're done.
          </p>

          <article className="card">
            <div className="card-body">
              <h2 style={{ margin: 0, fontSize: 20 }}>{created.title}</h2>
              <ol style={{ margin: '14px 0 0', paddingLeft: 20, lineHeight: 1.9 }}>
                {created.questions.map((q, i) => <li key={i}>{q}</li>)}
              </ol>
              <div className="hr" />
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  readOnly
                  value={inviteLink}
                  onFocus={e => e.target.select()}
                  style={{ flex: 1, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '10px 12px', color: 'inherit', fontSize: 13 }}
                  aria-label="Invite link"
                />
                <button className="btn btn-primary" onClick={copyLink}>
                  {copied ? 'Copied!' : 'Copy link'}
                </button>
              </div>
              {created.expires_at && (
                <p style={{ marginTop: 10, fontSize: 12, opacity: 0.6 }}>
                  This link stops working {formatDateTime(created.expires_at)}.
                </p>
              )}
              <div className="btn-row" style={{ marginTop: 18 }}>
                <Link to="/recruiter" className="btn btn-ghost">Back to dashboard</Link>
                <Link to="/recruiter/new" className="btn btn-primary">Create another</Link>
              </div>
            </div>
          </article>
        </main>
        <Toaster />
      </div>
    )
  }

  return (
    <div className="aura-pre-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      <nav className="nav" aria-label="Primary">
        <div className="nav-row">
          <Link to="/" className="brand" aria-label="Aura home">
            <span className="mark" aria-hidden="true"></span><span>Aura</span>
          </Link>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {user && (
              <span className="user-chip">
                <span className="avatar" aria-hidden="true">{initials(user.name || user.email)}</span>
                {user.name || user.email}
              </span>
            )}
            <button className="btn btn-ghost" onClick={logout} style={{ height: 32, padding: '0 14px', flex: 'none', fontSize: 13 }}>
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <main className="container">
        <span className="eyebrow"><span className="dot" aria-hidden="true"></span>New interview</span>
        <h1 className="h1">Set the <em>questions.</em></h1>
        <p className="lede">
          The AI interviewer asks exactly these questions. Keep it to 2–5 — that keeps each
          interview focused and inside your monthly quota.
        </p>

        <article className="card">
          <div className="card-body">
            <label className="label-row" htmlFor="invite-title">Role / position</label>
            <input
              id="invite-title"
              type="text"
              placeholder="e.g. Senior Backend Engineer"
              value={title}
              onChange={e => setTitle(e.target.value)}
              maxLength={200}
              style={{ width: '100%', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '12px 14px', color: 'inherit', fontSize: 14 }}
            />

            <label className="label-row" htmlFor="invite-context" style={{ marginTop: 18 }}>
              Job description or context <span style={{ opacity: 0.55 }}>(optional)</span>
            </label>
            <textarea
              id="invite-context"
              placeholder="Paste the job description or anything the interviewer should know — it steers how the questions are asked and how answers are evaluated."
              value={context}
              onChange={e => setContext(e.target.value)}
              rows={4}
              maxLength={4000}
              style={{ width: '100%', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '12px 14px', color: 'inherit', fontSize: 14, resize: 'vertical' }}
            />

            <div className="label-row" style={{ marginTop: 22 }}>
              Questions <span style={{ opacity: 0.55 }}>({questions.length} / {MAX_QUESTIONS})</span>
            </div>
            <div style={{ display: 'grid', gap: 10 }}>
              {questions.map((q, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ opacity: 0.5, fontSize: 13, width: 18, textAlign: 'right' }}>{idx + 1}.</span>
                  <input
                    type="text"
                    placeholder={`Question ${idx + 1}`}
                    value={q}
                    onChange={e => setQuestion(idx, e.target.value)}
                    maxLength={500}
                    style={{ flex: 1, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '11px 14px', color: 'inherit', fontSize: 14 }}
                    aria-label={`Question ${idx + 1}`}
                  />
                  {questions.length > MIN_QUESTIONS && (
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => removeQuestion(idx)}
                      aria-label={`Remove question ${idx + 1}`}
                      style={{ height: 36, padding: '0 10px' }}
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
            </div>

            <label className="label-row" htmlFor="invite-expiry" style={{ marginTop: 22 }}>
              Link expires after
            </label>
            <select
              id="invite-expiry"
              value={expiresInHours}
              onChange={e => setExpiresInHours(Number(e.target.value))}
              style={{ marginTop: 8, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '11px 14px', color: 'inherit', fontSize: 14 }}
            >
              {EXPIRY_OPTIONS.map(opt => (
                <option key={opt.hours} value={opt.hours} style={{ color: '#111' }}>
                  {opt.label}{opt.hours === DEFAULT_EXPIRY_HOURS ? ' (default)' : ''}
                </option>
              ))}
            </select>
            <p style={{ marginTop: 8, fontSize: 12, opacity: 0.55 }}>
              The candidate must start the interview within this window — after it passes the link stops working.
            </p>

            <div className="btn-row" style={{ marginTop: 20 }}>
              {questions.length < MAX_QUESTIONS && (
                <button className="btn btn-ghost" onClick={addQuestion}>+ Add question</button>
              )}
              <span style={{ flex: 1 }} />
              <button className="btn btn-primary" disabled={!valid || creating} onClick={submit}>
                {creating ? <><span className="spinner" /> Creating…</> : 'Create interview & link'}
              </button>
            </div>
            {!valid && (
              <p style={{ marginTop: 10, fontSize: 12, opacity: 0.55 }}>
                Add a role name and {MIN_QUESTIONS}–{MAX_QUESTIONS} non-empty questions to continue.
              </p>
            )}
          </div>
        </article>
      </main>
      <Toaster />
    </div>
  )
}
