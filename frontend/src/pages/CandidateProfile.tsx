import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  getCandidateProfile,
  saveCandidateProfile,
  uploadProfileResume,
  type ExperienceEntry,
  type EducationEntry,
} from '@/api/client'
import { AppHeader } from '@/components/layout/AppHeader'
import { useAuth } from '@/contexts/AuthContext'
import { apiErrorMessage } from '@/api/client'
import { mergeParsedIntoProfile, parsedHasContent, type ProfileFormState } from '@/lib/profile-utils'
import { Toaster } from '@/components/ui/toaster'
import { useToast } from '@/hooks/use-toast'
import '@/styles/aura-pre.css'

const MAX_SKILLS = 30

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 8,
  padding: '12px 14px',
  color: 'inherit',
  fontSize: 14,
}

export function CandidateProfile() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { toast } = useToast()

  const [form, setForm] = useState<ProfileFormState | null>(null)
  const [resumeStored, setResumeStored] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [skillDraft, setSkillDraft] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    getCandidateProfile()
      .then(p => {
        if (cancelled) return
        setForm({
          headline: p.headline,
          location: p.location,
          summary: p.summary,
          skills: p.skills,
          experience: p.experience,
          education: p.education,
          linkedin_url: p.linkedin_url,
          github_url: p.github_url,
          portfolio_url: p.portfolio_url,
        })
        setResumeStored(p.resume_stored)
      })
      .catch(err => {
        if (cancelled) return
        if (err?.response?.status === 401) navigate('/', { replace: true })
        setParseError('Failed to load your profile.')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [navigate])

  if (loading) {
    return (
      <div className="aura-pre-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <AppHeader />
        <main className="container">
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading profile…</span>
          </div>
        </main>
      </div>
    )
  }

  if (!form) {
    return (
      <div className="aura-pre-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <AppHeader />
        <main className="container">
          <div className="error-banner" role="alert">{parseError ?? 'Profile unavailable.'}</div>
        </main>
      </div>
    )
  }

  const set = <K extends keyof ProfileFormState>(key: K, value: ProfileFormState[K]) =>
    setForm(f => (f ? { ...f, [key]: value } : f))

  const addSkill = () => {
    const skill = skillDraft.trim().slice(0, 60)
    if (!skill) return
    if (form.skills.length >= MAX_SKILLS) return
    if (form.skills.some(s => s.toLowerCase() === skill.toLowerCase())) {
      setSkillDraft('')
      return
    }
    set('skills', [...form.skills, skill])
    setSkillDraft('')
  }

  const removeSkill = (skill: string) =>
    set('skills', form.skills.filter(s => s !== skill))

  const addExperience = () =>
    set('experience', [...form.experience, { title: '', company: '', start: '', end: '', description: '' }])

  const updateExperience = (idx: number, patch: Partial<ExperienceEntry>) =>
    set('experience', form.experience.map((e, i) => (i === idx ? { ...e, ...patch } : e)))

  const removeExperience = (idx: number) =>
    set('experience', form.experience.filter((_, i) => i !== idx))

  const addEducation = () =>
    set('education', [...form.education, { school: '', degree: '', field: '', start: '', end: '' }])

  const updateEducation = (idx: number, patch: Partial<EducationEntry>) =>
    set('education', form.education.map((e, i) => (i === idx ? { ...e, ...patch } : e)))

  const removeEducation = (idx: number) =>
    set('education', form.education.filter((_, i) => i !== idx))

  const handleResume = async (file: File) => {
    setParsing(true)
    setParseError(null)
    try {
      const { parsed, resume_stored } = await uploadProfileResume(file)
      setResumeStored(resume_stored)
      if (parsedHasContent(parsed)) {
        setForm(f => (f ? mergeParsedIntoProfile(f, parsed) : f))
        toast({
          title: 'Resume parsed',
          description: 'Empty fields were prefilled from your resume. Review and save.',
        })
      } else {
        toast({
          title: 'Resume stored',
          description: 'The PDF is on your profile, but nothing could be auto-extracted. Fill the form manually.',
          variant: 'destructive',
        })
      }
    } catch (error) {
      setParseError(apiErrorMessage(error, 'Could not read that resume. Try a text-based PDF.'))
    } finally {
      setParsing(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form) return
    setSaving(true)
    setSaveError(null)
    try {
      const saved = await saveCandidateProfile({
        headline: form.headline.trim(),
        location: form.location.trim(),
        summary: form.summary.trim(),
        skills: form.skills,
        experience: form.experience,
        education: form.education,
        linkedin_url: form.linkedin_url?.trim() || null,
        github_url: form.github_url?.trim() || null,
        portfolio_url: form.portfolio_url?.trim() || null,
      })
      setForm({
        headline: saved.headline,
        location: saved.location,
        summary: saved.summary,
        skills: saved.skills,
        experience: saved.experience,
        education: saved.education,
        linkedin_url: saved.linkedin_url,
        github_url: saved.github_url,
        portfolio_url: saved.portfolio_url,
      })
      toast({ title: 'Profile saved' })
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

      <main className="container" style={{ maxWidth: 860 }}>
        <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Candidate profile</span>
        <h1 className="h1">Your <em>profile.</em></h1>
        <p className="lede">
          This powers your interviews: Aura uses your skills and resume to ask sharper questions,
          and recruiters see who they're talking to. Upload your resume to autofill the form.
        </p>

        <form onSubmit={submit}>
          <article className="card">
            <div className="card-body">
              <div>
                <label className="label-row" htmlFor="cp-headline">Headline</label>
                <input
                  id="cp-headline"
                  type="text"
                  placeholder="e.g. Senior Backend Engineer | Python, Go"
                  value={form.headline}
                  onChange={e => set('headline', e.target.value)}
                  maxLength={200}
                  style={inputStyle}
                />
              </div>

              <div>
                <label className="label-row" htmlFor="cp-location">Location</label>
                <input
                  id="cp-location"
                  type="text"
                  placeholder="e.g. Berlin, Germany (open to remote)"
                  value={form.location}
                  onChange={e => set('location', e.target.value)}
                  maxLength={120}
                  style={inputStyle}
                />
              </div>

              <div>
                <label className="label-row" htmlFor="cp-summary">Summary</label>
                <textarea
                  id="cp-summary"
                  placeholder="A few sentences about your experience, what you're strong at, and what you're looking for."
                  value={form.summary}
                  onChange={e => set('summary', e.target.value)}
                  rows={4}
                  maxLength={4000}
                  style={{ ...inputStyle, resize: 'vertical' }}
                />
              </div>

              <div>
                <label className="label-row" htmlFor="cp-skill">Skills <span style={{ opacity: 0.55 }}>({form.skills.length} / {MAX_SKILLS})</span></label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    id="cp-skill"
                    type="text"
                    placeholder="Type a skill and press Enter"
                    value={skillDraft}
                    onChange={e => setSkillDraft(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addSkill()
                      }
                    }}
                    maxLength={60}
                    style={inputStyle}
                  />
                  <button type="button" className="btn btn-ghost" onClick={addSkill} style={{ height: 42 }}>Add</button>
                </div>
                {form.skills.length > 0 && (
                  <div className="skill-tags" style={{ marginTop: 10 }}>
                    {form.skills.map(skill => (
                      <button
                        key={skill}
                        type="button"
                        className="skill-tag"
                        onClick={() => removeSkill(skill)}
                        aria-label={`Remove skill ${skill}`}
                        style={{ cursor: 'pointer' }}
                      >
                        {skill} ✕
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div className="label-row">Links</div>
                <div style={{ display: 'grid', gap: 10 }}>
                  <input
                    type="url"
                    placeholder="LinkedIn profile (https://…)"
                    value={form.linkedin_url ?? ''}
                    onChange={e => set('linkedin_url', e.target.value || null)}
                    maxLength={512}
                    style={inputStyle}
                    aria-label="LinkedIn URL"
                  />
                  <input
                    type="url"
                    placeholder="GitHub profile (https://…)"
                    value={form.github_url ?? ''}
                    onChange={e => set('github_url', e.target.value || null)}
                    maxLength={512}
                    style={inputStyle}
                    aria-label="GitHub URL"
                  />
                  <input
                    type="url"
                    placeholder="Portfolio / personal site (https://…)"
                    value={form.portfolio_url ?? ''}
                    onChange={e => set('portfolio_url', e.target.value || null)}
                    maxLength={512}
                    style={inputStyle}
                    aria-label="Portfolio URL"
                  />
                </div>
              </div>
            </div>
          </article>

          <article className="card" style={{ marginTop: 20 }}>
            <div className="card-body">
              <div className="label-row">Experience</div>
              {form.experience.map((entry, idx) => (
                <div key={idx} style={{ border: '1px solid rgba(255,255,255,0.10)', borderRadius: 10, padding: 16, display: 'grid', gap: 10 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <input type="text" placeholder="Job title" value={entry.title} onChange={e => updateExperience(idx, { title: e.target.value })} maxLength={120} style={inputStyle} aria-label={`Job title (position ${idx + 1})`} />
                    <input type="text" placeholder="Company" value={entry.company} onChange={e => updateExperience(idx, { company: e.target.value })} maxLength={120} style={inputStyle} aria-label={`Company (position ${idx + 1})`} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <input type="text" placeholder="Start (e.g. 2022-03)" value={entry.start} onChange={e => updateExperience(idx, { start: e.target.value })} maxLength={40} style={inputStyle} aria-label={`Start date (position ${idx + 1})`} />
                    <input type="text" placeholder="End (or 'Present')" value={entry.end} onChange={e => updateExperience(idx, { end: e.target.value })} maxLength={40} style={inputStyle} aria-label={`End date (position ${idx + 1})`} />
                  </div>
                  <textarea placeholder="What you built, led, or owned" value={entry.description} onChange={e => updateExperience(idx, { description: e.target.value })} rows={2} maxLength={2000} style={{ ...inputStyle, resize: 'vertical' }} aria-label={`Description (position ${idx + 1})`} />
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button type="button" className="btn btn-ghost" onClick={() => removeExperience(idx)}>Remove</button>
                  </div>
                </div>
              ))}
              <button type="button" className="btn btn-ghost" onClick={addExperience}>+ Add experience</button>
            </div>
          </article>

          <article className="card" style={{ marginTop: 20 }}>
            <div className="card-body">
              <div className="label-row">Education</div>
              {form.education.map((entry, idx) => (
                <div key={idx} style={{ border: '1px solid rgba(255,255,255,0.10)', borderRadius: 10, padding: 16, display: 'grid', gap: 10 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <input type="text" placeholder="School" value={entry.school} onChange={e => updateEducation(idx, { school: e.target.value })} maxLength={160} style={inputStyle} aria-label={`School (education ${idx + 1})`} />
                    <input type="text" placeholder="Degree" value={entry.degree} onChange={e => updateEducation(idx, { degree: e.target.value })} maxLength={160} style={inputStyle} aria-label={`Degree (education ${idx + 1})`} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                    <input type="text" placeholder="Field" value={entry.field} onChange={e => updateEducation(idx, { field: e.target.value })} maxLength={160} style={inputStyle} aria-label={`Field of study (education ${idx + 1})`} />
                    <input type="text" placeholder="Start" value={entry.start} onChange={e => updateEducation(idx, { start: e.target.value })} maxLength={40} style={inputStyle} aria-label={`Start year (education ${idx + 1})`} />
                    <input type="text" placeholder="End" value={entry.end} onChange={e => updateEducation(idx, { end: e.target.value })} maxLength={40} style={inputStyle} aria-label={`End year (education ${idx + 1})`} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button type="button" className="btn btn-ghost" onClick={() => removeEducation(idx)}>Remove</button>
                  </div>
                </div>
              ))}
              <button type="button" className="btn btn-ghost" onClick={addEducation}>+ Add education</button>
            </div>
          </article>

          <article className="card" style={{ marginTop: 20 }}>
            <div className="card-body">
              <div className="label-row">Resume</div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>
                {resumeStored
                  ? 'A resume is on file — you can start interviews without re-uploading. Upload again to replace it and re-run autofill.'
                  : 'Upload your resume to autofill this profile and start interviews without re-uploading.'}
              </p>
              <label className="dropzone" data-has-file={resumeStored}>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf"
                  disabled={parsing}
                  onChange={e => {
                    const file = e.target.files?.[0]
                    if (file) handleResume(file)
                  }}
                />
                <div className="title">{parsing ? 'Parsing your resume…' : resumeStored ? 'Resume on file' : 'Upload resume (PDF)'}</div>
                <div className="hint">max 10 MB · text-based PDF works best</div>
                {resumeStored && <div className="filename">✓ resume.pdf stored</div>}
              </label>
              {parseError && <div className="error-banner" role="alert">{parseError}</div>}
            </div>
          </article>

          {saveError && <div className="error-banner" role="alert" style={{ marginTop: 16 }}>{saveError}</div>}

          <div className="btn-row" style={{ marginTop: 20, marginBottom: 60 }}>
            <Link to={user?.role === '' ? '/choose-role' : '/interview'} className="btn btn-ghost">Back</Link>
            <span style={{ flex: 1 }} />
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? <><span className="spinner" /> Saving…</> : 'Save profile'}
            </button>
          </div>
        </form>
      </main>
      <Toaster />
    </div>
  )
}
