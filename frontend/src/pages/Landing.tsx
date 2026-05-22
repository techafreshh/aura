import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import '@/styles/aura-landing.css'

const ORB_STATES = [
  { state: 'listening', label: 'listening' },
  { state: 'thinking', label: 'thinking' },
  { state: 'speaking', label: 'speaking' },
] as const

export function Landing() {
  const pageRef = useRef<HTMLDivElement>(null)
  const [orbIdx, setOrbIdx] = useState(0)
  const [labelFading, setLabelFading] = useState(false)

  // Cursor-tracking spotlight + orb parallax via CSS variables
  useEffect(() => {
    const el = pageRef.current
    if (!el) return
    let raf = 0
    let lastX = window.innerWidth / 2
    let lastY = window.innerHeight / 2

    const onMove = (e: PointerEvent) => {
      lastX = e.clientX
      lastY = e.clientY
      if (raf) return
      raf = requestAnimationFrame(() => {
        el.style.setProperty('--mx', `${lastX}px`)
        el.style.setProperty('--my', `${lastY}px`)
        raf = 0
      })
    }
    window.addEventListener('pointermove', onMove)
    return () => {
      window.removeEventListener('pointermove', onMove)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [])

  // Cycle orb status: listening → thinking → speaking
  useEffect(() => {
    const t = setInterval(() => {
      setLabelFading(true)
      setTimeout(() => {
        setOrbIdx(i => (i + 1) % ORB_STATES.length)
        setLabelFading(false)
      }, 280)
    }, 3200)
    return () => clearInterval(t)
  }, [])

  // Scroll reveal: add .is-in class once the element enters viewport
  useEffect(() => {
    const el = pageRef.current
    if (!el) return
    const targets = el.querySelectorAll('.reveal, .reveal-stagger')
    if (!('IntersectionObserver' in window) || targets.length === 0) {
      targets.forEach(t => t.classList.add('is-in'))
      return
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach(en => {
        if (en.isIntersecting) {
          en.target.classList.add('is-in')
          io.unobserve(en.target)
        }
      })
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.12 })
    targets.forEach(t => io.observe(t))
    return () => io.disconnect()
  }, [])

  // Per-card cursor variables for 3D hover tilt
  const handleCardMove = (e: React.PointerEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    e.currentTarget.style.setProperty('--cx', `${((e.clientX - r.left) / r.width) * 100}%`)
    e.currentTarget.style.setProperty('--cy', `${((e.clientY - r.top) / r.height) * 100}%`)
  }
  const handleCardLeave = (e: React.PointerEvent<HTMLElement>) => {
    e.currentTarget.style.setProperty('--cx', '50%')
    e.currentTarget.style.setProperty('--cy', '50%')
  }

  const orbStatus = ORB_STATES[orbIdx]

  return (
    <div className="aura-landing-page" ref={pageRef}>
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>
      <div className="cursor-spotlight" aria-hidden="true"></div>

      <header className="nav" role="banner">
        <div className="container nav-row">
          <a href="#" className="brand" aria-label="Aura, AI interviewer">
            <span className="mark" aria-hidden="true"></span><span>Aura</span>
          </a>
          <nav className="nav-links" aria-label="Primary">
            <a href="#features">Product</a>
            <a href="#stack">Platform</a>
          </nav>
          <div className="nav-cta">
            <Link to="/interview" className="btn btn-sm btn-primary">
              Get started
              <svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </Link>
          </div>
        </div>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <div className="container hero-grid">
          <div className="reveal">
            <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Real-time voice interviews</span>
            <h1 id="hero-title" className="display">The first interview,<br/><em>automated by intelligence.</em></h1>
            <p className="lede">Scale your hiring with Aura. Real-time voice interviews that probe deeper, evaluate fairer, and report faster — so your team only meets the candidates worth meeting.</p>
            <div className="hero-cta">
              <Link to="/interview" className="btn btn-lg btn-primary">
                Start a Mock Interview
                <svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </Link>
              <a
                href="https://github.com/your-username/AI-Interviewer"
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-lg btn-ghost btn-github"
                aria-label="Star Aura on GitHub"
              >
                <span className="gh-label">
                  <svg className="gh-icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" clipRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/>
                  </svg>
                  Star on GitHub
                </span>
                <span className="gh-count">
                  <svg className="star-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M12 2.5l3.09 6.26L22 9.77l-5 4.87 1.18 6.88L12 18.27l-6.18 3.25L7 14.64l-5-4.87 6.91-1.01L12 2.5z"/>
                  </svg>
                  Star
                </span>
              </a>
            </div>
            <div className="hero-meta">
              <span>LiveKit voice</span>
              <span className="sep" aria-hidden="true"></span>
              <span>Pydantic AI evaluation</span>
              <span className="sep" aria-hidden="true"></span>
              <span>Resume-calibrated</span>
            </div>
          </div>

          <div className="orb-stage reveal" role="img" aria-label="Aura, an indigo orb pulsing with concentric rings">
            <div className="glow-outer" aria-hidden="true"></div>
            <div className="ring-set" aria-hidden="true">
              <div className="ring r1"></div>
              <div className="ring r2"></div>
              <div className="ring r3"></div>
              <div className="ring r4"></div>
            </div>
            <div className="streaks" aria-hidden="true">
              <span className="streak" style={{ '--a': '18deg' } as React.CSSProperties}></span>
              <span className="streak" style={{ '--a': '74deg', animationDelay: '1.2s' } as React.CSSProperties}></span>
              <span className="streak" style={{ '--a': '142deg', animationDelay: '2.6s' } as React.CSSProperties}></span>
              <span className="streak" style={{ '--a': '212deg', animationDelay: '0.6s' } as React.CSSProperties}></span>
              <span className="streak" style={{ '--a': '286deg', animationDelay: '3.4s' } as React.CSSProperties}></span>
              <span className="streak" style={{ '--a': '332deg', animationDelay: '4.6s' } as React.CSSProperties}></span>
            </div>
            <div className="core" aria-hidden="true"></div>
            <div className="dust" aria-hidden="true">
              <span style={{ top: '12%', left: '78%', animationDelay: '0s' }}></span>
              <span style={{ top: '30%', left: '14%', animationDelay: '1.2s' }}></span>
              <span style={{ top: '76%', left: '22%', animationDelay: '2.4s' }}></span>
              <span style={{ top: '84%', left: '64%', animationDelay: '0.6s' }}></span>
              <span style={{ top: '18%', left: '50%', animationDelay: '3.2s' }}></span>
              <span style={{ top: '58%', left: '88%', animationDelay: '4.4s' }}></span>
              <span style={{ top: '42%', left: '8%', animationDelay: '1.8s' }}></span>
              <span style={{ top: '8%', left: '32%', animationDelay: '2.8s' }}></span>
            </div>
            <div className="orb-status" aria-hidden="true" data-state={orbStatus.state}>
              <span className="pulse"></span>
              <span className={`label ${labelFading ? 'fading' : ''}`}>Aura · {orbStatus.label}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="features" aria-labelledby="features-title">
        <div className="container">
          <div className="section-head reveal">
            <span className="kicker">Capabilities</span>
            <h2 id="features-title" className="h2">A complete intake-to-report loop, in a single conversation.</h2>
            <p className="lede-2 lede">Three capabilities, working together. From the moment a resume is uploaded to the moment your hiring manager opens the report.</p>
          </div>

          <div className="bento reveal-stagger">
            <article className="card card-resume" onPointerMove={handleCardMove} onPointerLeave={handleCardLeave}>
              <div className="card-body">
                <span className="label">01 — Intake</span>
                <h3>Resume Intelligence</h3>
                <p>Upload any PDF. Aura builds a custom interview plan in seconds — calibrated to the role, the candidate's claimed experience, and the gaps worth probing.</p>
                <div className="mock">
                  <div className="resume-mock">
                    <div className="resume-doc">
                      <div className="file-tab">resume_dahlia_chen.pdf</div>
                      <div className="name">Dahlia Chen</div>
                      <div className="role">Senior Backend Engineer · 6 yrs</div>
                      <div className="bar full"></div>
                      <div className="bar med"></div>
                      <div className="bar full"></div>
                      <div className="bar short"></div>
                      <div className="bar med"></div>
                      <div className="skill-tags">
                        <span className="tag">Go</span>
                        <span className="tag">Postgres</span>
                        <span className="tag">Kafka</span>
                        <span className="tag">gRPC</span>
                        <span className="tag">k8s</span>
                      </div>
                      <div className="resume-arrow" aria-hidden="true">
                        <svg viewBox="0 0 16 16" fill="none">
                          <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </div>
                    </div>
                    <div className="resume-rubric">
                      <div className="rubric-head"><span>Generated plan</span><span className="live">Building</span></div>
                      {[
                        ['Distributed systems depth', '0.30', false],
                        ['Kafka — claimed, probe specifics', '0.22', false],
                        ['API design & versioning', '0.18', false],
                        ['Data modeling for scale', '0.18', true],
                        ['Communication clarity', '0.12', true],
                      ].map(([label, weight, pending], i) => (
                        <div key={i} className={`rubric-item ${pending ? 'pending' : ''}`}>
                          <span className="check">
                            <svg viewBox="0 0 12 12" fill="none">
                              <path d="M2.5 6.5 5 9l4.5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                          </span>
                          <span>{label}</span>
                          <span className="weight">{weight}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </article>

            <article className="card card-voice" onPointerMove={handleCardMove} onPointerLeave={handleCardLeave}>
              <div className="card-body">
                <span className="label">02 — Conversation</span>
                <h3>Low-Latency Voice</h3>
                <p>Zero lag. Natural conversations powered by LiveKit and native LLMs — Aura interrupts, clarifies, and follows up the way a senior engineer would.</p>
                <div className="mock">
                  <div className="voice-mock">
                    <div className="voice-row">
                      <span>WSS · candidate ⇄ aura</span>
                      <span className="latency" style={{ marginLeft: 'auto' }}>12ms</span>
                    </div>
                    <div className="wave" aria-hidden="true">
                      {[30, 60, 80, 50, 90, 70, 100, 55, 75, 40, 65, 85, 45, 70, 30, 60, 90, 50].map((h, i) => (
                        <span key={i} className="bar" style={{ height: `${h}%`, animationDelay: `-${(i % 7 + 1) * 0.1}s` }}></span>
                      ))}
                    </div>
                    <div className="voice-transcript">
                      <div className="line aura">
                        <span className="who">aura</span>
                        <span className="what">You mentioned a Kafka migration last year — what made the previous queue insufficient?</span>
                      </div>
                      <div className="line">
                        <span className="who">candidate</span>
                        <span className="what">Throughput. We were hitting partition limits on RabbitMQ around—</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </article>

            <article className="card card-report" onPointerMove={handleCardMove} onPointerLeave={handleCardLeave}>
              <div className="card-body">
                <span className="label">03 — Output</span>
                <h3>In-Depth Reporting</h3>
                <p>Objective, structured data on every candidate. No more bias, just performance — a clean recommendation your team can act on.</p>
                <div className="mock">
                  <div className="report-mock">
                    <div className="candidate-row">
                      <div className="avatar" aria-hidden="true">DC</div>
                      <div>
                        <div className="name">Dahlia Chen</div>
                        <div className="role">Sr. Backend Engineer</div>
                      </div>
                      <span className="score">8.7 / 10</span>
                    </div>
                    {[
                      { label: 'Distributed', w: 92, v: '9.2' },
                      { label: 'API design', w: 84, v: '8.4' },
                      { label: 'Data modeling', w: 78, v: '7.8' },
                      { label: 'Communication', w: 88, v: '8.8' },
                    ].map((m, i) => (
                      <div key={i} className="metric">
                        <span className="label-m">{m.label}</span>
                        <span className="track"><span className="fill" style={{ width: `${m.w}%` }}></span></span>
                        <span className="val">{m.v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section className="proof reveal" id="stack" aria-labelledby="stack-title">
        <div className="container proof-row">
          <div className="proof-label" id="stack-title">Built on</div>
          <div className="stack-row">
            <a href="#" className="logo-mark" aria-label="LiveKit">
              <span className="glyph">
                <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor">
                  <rect x="1" y="6" width="3" height="4" rx="0.5"/>
                  <rect x="6" y="3" width="3" height="10" rx="0.5"/>
                  <rect x="11" y="6" width="3" height="4" rx="0.5"/>
                </svg>
              </span>
              <span>LiveKit</span>
            </a>
            <a href="#" className="logo-mark" aria-label="Pydantic AI">
              <span className="glyph">{'{ }'}</span>
              <span>Pydantic AI</span>
            </a>
            <a href="#" className="logo-mark" aria-label="OpenAI">
              <span className="glyph">
                <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="8" cy="8" r="6.2"/><path d="M8 1.8v12.4M1.8 8h12.4"/>
                </svg>
              </span>
              <span>OpenAI</span>
            </a>
            <a href="#" className="logo-mark" aria-label="Deepgram">
              <span className="glyph">
                <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                  <path d="M2 8a6 6 0 1 1 12 0 6 6 0 0 1-12 0Zm6-3.6L4.8 8 8 11.6 11.2 8 8 4.4Z"/>
                </svg>
              </span>
              <span>Deepgram</span>
            </a>
          </div>
        </div>
      </section>

      <section className="cta-section reveal" id="start" aria-labelledby="cta-title">
        <div className="cta-bg" aria-hidden="true"></div>
        <div className="container">
          <div className="cta-mini-orb" aria-hidden="true"></div>
          <h2 id="cta-title">Meet your next senior interviewer.</h2>
          <p>Upload a resume and run a real voice interview. Walk away with a real transcript and a real report.</p>
          <div className="cta-actions">
            <Link to="/interview" className="btn btn-lg btn-primary">
              Start a Mock Interview
              <svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </Link>
          </div>
        </div>
      </section>

      <footer className="footer">
        <div className="container footer-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span className="brand" style={{ color: 'var(--fg-2)' }}>
              <span className="mark" aria-hidden="true"></span><span>Aura</span>
            </span>
            <span className="footer-meta" style={{ marginLeft: '16px' }}>© 2026 Aura</span>
          </div>
          <div className="footer-meta">v1.0</div>
        </div>
      </footer>
    </div>
  )
}
