import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { getRecruiterProfile, saveRecruiterProfile } from '@/api/client'
import { AppHeader } from '@/components/layout/AppHeader'
import { apiErrorMessage } from '@/api/client'
import { Toaster } from '@/components/ui/toaster'
import { useToast } from '@/hooks/use-toast'
import '@/styles/aura-pre.css'

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 8,
  padding: '12px 14px',
  color: 'inherit',
  fontSize: 14,
}

export function RecruiterProfile() {
  const navigate = useNavigate()
  const { toast } = useToast()

  const [companyName, setCompanyName] = useState('')
  const [jobTitle, setJobTitle] = useState('')
  const [companyWebsite, setCompanyWebsite] = useState('')
  const [companyLocation, setCompanyLocation] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getRecruiterProfile()
      .then(p => {
        if (cancelled) return
        setCompanyName(p.company_name)
        setJobTitle(p.job_title)
        setCompanyWebsite(p.company_website ?? '')
        setCompanyLocation(p.company_location)
      })
      .catch(err => {
        if (cancelled) return
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          navigate('/', { replace: true })
          return
        }
        setLoadError('Failed to load your profile.')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [navigate])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    try {
      await saveRecruiterProfile({
        company_name: companyName.trim(),
        job_title: jobTitle.trim(),
        company_website: companyWebsite.trim() || null,
        company_location: companyLocation.trim(),
      })
      toast({ title: 'Company profile saved', description: 'Candidates see your name and company on interview invites.' })
    } catch (error) {
      setSaveError(apiErrorMessage(error, 'Could not save your profile.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="aura-pre-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      <AppHeader active="profile" />

      <main className="container" style={{ maxWidth: 640 }}>
        <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Recruiter profile</span>
        <h1 className="h1">Company <em>profile.</em></h1>
        <p className="lede">
          Your name and company show up on every invite you send, so candidates know who they're
          interviewing with before they start.
        </p>

        {loading ? (
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading profile…</span>
          </div>
        ) : (
          <form onSubmit={submit}>
            <article className="card">
              <div className="card-body">
                <div>
                  <label className="label-row" htmlFor="rp-company">Company name</label>
                  <input
                    id="rp-company"
                    type="text"
                    placeholder="e.g. Acme Robotics"
                    value={companyName}
                    onChange={e => setCompanyName(e.target.value)}
                    maxLength={200}
                    style={inputStyle}
                  />
                </div>

                <div>
                  <label className="label-row" htmlFor="rp-title">Your title</label>
                  <input
                    id="rp-title"
                    type="text"
                    placeholder="e.g. Engineering Manager"
                    value={jobTitle}
                    onChange={e => setJobTitle(e.target.value)}
                    maxLength={120}
                    style={inputStyle}
                  />
                </div>

                <div>
                  <label className="label-row" htmlFor="rp-website">Company website</label>
                  <input
                    id="rp-website"
                    type="url"
                    placeholder="https://acme.example"
                    value={companyWebsite}
                    onChange={e => setCompanyWebsite(e.target.value)}
                    maxLength={512}
                    style={inputStyle}
                  />
                </div>

                <div>
                  <label className="label-row" htmlFor="rp-location">Company location</label>
                  <input
                    id="rp-location"
                    type="text"
                    placeholder="e.g. Remote / Berlin"
                    value={companyLocation}
                    onChange={e => setCompanyLocation(e.target.value)}
                    maxLength={120}
                    style={inputStyle}
                  />
                </div>
              </div>
            </article>

            {saveError && <div className="error-banner" role="alert" style={{ marginTop: 16 }}>{saveError}</div>}
            {loadError && <div className="error-banner" role="alert" style={{ marginTop: 16 }}>{loadError}</div>}

            <div className="btn-row" style={{ marginTop: 20, marginBottom: 60 }}>
              <span style={{ flex: 1 }} />
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? <><span className="spinner" /> Saving…</> : 'Save profile'}
              </button>
            </div>
          </form>
        )}
      </main>
      <Toaster />
    </div>
  )
}
