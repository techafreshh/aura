import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useInterview } from '@/hooks/use-interview'
import { uploadResume, getToken } from '@/api/client'
import { InterviewAgent } from '@/components/voice/InterviewAgent'
import { ReportView } from '@/components/interview/ReportView'
import { Toaster } from '@/components/ui/toaster'
import { useToast } from '@/hooks/use-toast'
import '@/styles/aura-pre.css'

export function InterviewFlow() {
  const { step, sessionId, plan, report, startPreview, startInterview, showReport, reset } = useInterview()
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)
  const { toast } = useToast()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setFile(e.target.files[0])
  }

  const handleUpload = async () => {
    if (!file) return
    setIsUploading(true)
    try {
      const data = await uploadResume(file)
      startPreview(data)
      toast({ title: "Resume parsed", description: `Plan ready for ${data.plan_summary.candidate_name}.` })
    } catch (error) {
      toast({ title: "Upload failed", description: error instanceof Error ? error.message : "Upload a valid PDF.", variant: "destructive" })
    } finally { setIsUploading(false) }
  }

  const handleJoin = async () => {
    if (!sessionId) return
    setIsConnecting(true)
    try {
      const t = await getToken(sessionId)
      setToken(t)
      startInterview()
    } catch {
      toast({ title: "Connection failed", description: "Could not get access token.", variant: "destructive" })
    } finally { setIsConnecting(false) }
  }

  // Interview takes over fullscreen
  if (step === 'INTERVIEW' && token && sessionId) {
    return <InterviewAgent token={token} sessionId={sessionId} candidateName={plan?.candidate_name} onInterviewEnd={showReport} />
  }

  if (step === 'REPORT' && report) {
    return <ReportView report={report} onDone={reset} />
  }

  return (
    <div className="aura-pre-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      {/* Nav */}
      <nav className="nav" aria-label="Primary">
        <div className="nav-row">
          <Link to="/" className="brand" aria-label="Aura home">
            <span className="mark" aria-hidden="true"></span><span>Aura</span>
          </Link>
          {step !== 'UPLOAD' && (
            <button className="btn btn-ghost" onClick={reset} style={{ height: 32, padding: '0 14px', flex: 'none', fontSize: 13 }}>
              Cancel
            </button>
          )}
        </div>
      </nav>

      {/* UPLOAD */}
      {step === 'UPLOAD' && (
        <main className="container">
          <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Step 1 — Intake</span>
          <h1 className="h1">Upload a <em>resume.</em></h1>
          <p className="lede">Aura builds a personalized interview plan from the candidate's PDF in a few seconds.</p>

          <article className="card">
            <div className="card-body">
              <label className="dropzone" data-has-file={file ? "true" : "false"}>
                <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <div className="title">Drop your PDF here, or click to browse</div>
                <div className="hint">PDF only · max 10 MB</div>
                {file && (
                  <div className="filename">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                    {file.name}
                  </div>
                )}
                <input type="file" accept=".pdf" onChange={handleFileChange} />
              </label>

              <div className="btn-row">
                <button className="btn btn-primary" disabled={!file || isUploading} onClick={handleUpload}>
                  {isUploading ? <><span className="spinner" /> Parsing resume…</> : "Prepare Interview"}
                </button>
              </div>
            </div>
          </article>
        </main>
      )}

      {/* PREVIEW */}
      {step === 'PREVIEW' && plan && (
        <main className="container wide">
          <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Step 2 — Plan</span>
          <h1 className="h1">Ready when <em>you are.</em></h1>
          <p className="lede">Here's what Aura will explore in the conversation. You can start the interview when you're ready.</p>

          <article className="card">
            <div className="card-body">
              <div className="preview-head">
                <div className="avatar">{plan.candidate_name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() || 'C'}</div>
                <div>
                  <h2 className="name">{plan.candidate_name}</h2>
                  <div className="sub">Voice interview · approx. 10–15 min</div>
                </div>
              </div>

              <div className="hr" />

              <div>
                <div className="label-row">Identified skills</div>
                <div className="skill-tags">
                  {plan.extracted_skills.map((s, i) => <span key={i} className="skill-tag">{s}</span>)}
                </div>
              </div>

              <div className="btn-row">
                <button className="btn btn-ghost" onClick={reset}>Cancel</button>
                <button className="btn btn-primary" onClick={handleJoin} disabled={isConnecting}>
                  {isConnecting ? <><span className="spinner" /> Connecting…</> : (
                    <>
                      Start Voice Interview
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                        <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </>
                  )}
                </button>
              </div>
            </div>
          </article>
        </main>
      )}

      <Toaster />
    </div>
  )
}
