import type { FinalReport } from "@/api/client";
import { downloadArtifact } from "@/api/client";
import { useRef, useState, useEffect } from "react";
import { Link } from "react-router-dom";
import jsPDF from "jspdf";
import html2canvas from "html2canvas";
import "@/styles/aura-report.css";

interface ReportViewProps {
  report: FinalReport;
  sessionId: string;
  onDone: () => void;
}

const recPill = (rec: string) => {
  switch (rec) {
    case "Strong Hire": return { cls: "pill pill-success", text: "Strong Hire" };
    case "Hire":        return { cls: "pill pill-success", text: "Hire" };
    case "Hold":        return { cls: "pill pill-warn",    text: "Hold" };
    case "No Hire":     return { cls: "pill pill-danger",  text: "No Hire" };
    default:            return { cls: "pill",              text: rec };
  }
};

export function ReportView({ report, sessionId, onDone }: ReportViewProps) {
  const captureRef = useRef<HTMLDivElement>(null);
  const [exporting, setExporting] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const initials = report.candidate_name.split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase() || "C";
  const rec = recPill(report.recommendation);
  const overallPct = Math.max(0, Math.min(100, report.overall_score));
  const generatedDate = new Date().toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

  const handleExportPDF = async () => {
    const node = captureRef.current;
    if (!node) return;
    setExporting(true);

    // Pin a fixed export width so layout is deterministic regardless of viewport
    const EXPORT_WIDTH = 1240;

    // Snapshot inline styles we will mutate, then restore after capture
    const originalCss = node.style.cssText;
    node.style.width = `${EXPORT_WIDTH}px`;
    node.style.maxWidth = `${EXPORT_WIDTH}px`;
    node.style.background = "#09090b";

    try {
      const canvas = await html2canvas(node, {
        backgroundColor: "#09090b",
        scale: 2,
        useCORS: true,
        logging: false,
        windowWidth: EXPORT_WIDTH,
        windowHeight: node.scrollHeight,
        onclone: (clonedDoc) => {
          // Inject safe CSS overrides into the cloned document so html2canvas
          // (which doesn't support modern CSS like -webkit-background-clip:text,
          // backdrop-filter, mask-composite, conic-gradient borders, or
          // aspect-ratio in some flows) renders predictably.
          const style = clonedDoc.createElement("style");
          style.textContent = `
            .aura-report-page * {
              backdrop-filter: none !important;
              -webkit-backdrop-filter: none !important;
              text-wrap: normal !important;
            }
            /* Hide chrome that lives outside the captured tree but might leak through */
            .aura-report-page .nav,
            .aura-report-page .page-ambient,
            .aura-report-page .grid-mesh { display: none !important; }
            /* Replace gradient text with solid color (browser doesn't render it correctly in capture) */
            .aura-report-page .page-h1,
            .aura-report-page .page-h1 em,
            .aura-report-page .score-num {
              background: none !important;
              -webkit-background-clip: initial !important;
              background-clip: initial !important;
              color: #fafafa !important;
              -webkit-text-fill-color: #fafafa !important;
            }
            .aura-report-page .score-num .denom {
              color: #71717a !important;
              -webkit-text-fill-color: #71717a !important;
            }
            /* Card glow uses mask-composite trickery — hide its overlay */
            .aura-report-page .card.glow::before { display: none !important; }
            /* Force an explicit fixed size on the score ring so aspect-ratio doesn't trip up the capture */
            .aura-report-page .score-ring-wrap {
              width: 240px !important;
              height: 240px !important;
              max-width: 240px !important;
              aspect-ratio: auto !important;
            }
            /* Avoid any sticky positioning artifacts */
            .aura-report-page .nav { position: static !important; }
            /* Solid surfaces for cards (was relying on backdrop-filter for translucency) */
            .aura-report-page .card { background: #131318 !important; }
            .aura-report-page .action-bar { background: #131318 !important; }
            /* Tabular numerics off (some font features confuse capture) */
            .aura-report-page { font-variant-numeric: normal !important; }
          `;
          clonedDoc.head.appendChild(style);
        },
      });

      // Build a portrait PDF that fits the captured canvas at letter-ish proportions
      const imgData = canvas.toDataURL("image/png");
      // Use a points-based PDF (A4 portrait) and scale image to width
      const pdf = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" });
      const pageW = pdf.internal.pageSize.getWidth();
      const pageH = pdf.internal.pageSize.getHeight();
      const margin = 24;
      const printableW = pageW - margin * 2;
      const ratio = canvas.height / canvas.width;
      const drawW = printableW;
      const drawH = drawW * ratio;

      // If the rendered image is taller than the page, paginate by drawing the
      // image multiple times with a clipping window using addImage's positioning.
      if (drawH <= pageH - margin * 2) {
        pdf.addImage(imgData, "PNG", margin, margin, drawW, drawH, undefined, "FAST");
      } else {
        // Multi-page paginate
        const pageImgH = pageH - margin * 2;
        // Convert pageImgH back into source-pixel slices
        const pxPerPt = canvas.width / drawW;
        const pageImgPx = pageImgH * pxPerPt;
        let yPx = 0;
        let isFirst = true;
        while (yPx < canvas.height) {
          const sliceH = Math.min(pageImgPx, canvas.height - yPx);
          // Render a slice via a temporary canvas
          const slice = document.createElement("canvas");
          slice.width = canvas.width;
          slice.height = sliceH;
          const ctx = slice.getContext("2d");
          if (ctx) {
            ctx.fillStyle = "#09090b";
            ctx.fillRect(0, 0, slice.width, slice.height);
            ctx.drawImage(canvas, 0, -yPx);
          }
          const sliceData = slice.toDataURL("image/png");
          if (!isFirst) pdf.addPage();
          isFirst = false;
          const sliceDrawH = (sliceH / pxPerPt);
          pdf.addImage(sliceData, "PNG", margin, margin, drawW, sliceDrawH, undefined, "FAST");
          yPx += sliceH;
        }
      }

      pdf.save(`aura-report-${report.candidate_name.replace(/\s+/g, "-").toLowerCase()}.pdf`);
    } catch (err) {
      console.error("PDF export failed:", err);
      alert("PDF export failed. Check console.");
    } finally {
      node.style.cssText = originalCss;
      setExporting(false);
    }
  };

  return (
    <div className="aura-report-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      {/* Nav */}
      <nav className="nav" aria-label="Primary">
        <div className="nav-row">
          <Link to="/" className="brand" aria-label="Aura home">
            <span className="mark" aria-hidden="true"></span><span>Aura</span>
          </Link>
          <div className="breadcrumb" aria-label="Breadcrumb">
            <span>Reports</span>
            <span className="sep">/</span>
            <span className="current">{report.candidate_name}</span>
          </div>
          <div className="nav-actions">
            <div className="dropdown" ref={dropdownRef} style={{ position: "relative" }}>
              <button className="btn-icon" aria-label="Download" onClick={() => setDropdownOpen(!dropdownOpen)} title="Download">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
              </button>
              {dropdownOpen && (
                <div className="dropdown-menu" style={{ position: "absolute", right: 0, top: "100%", marginTop: 4, background: "#1c1c22", border: "1px solid #27272a", borderRadius: 8, padding: "4px 0", zIndex: 50, minWidth: 160 }}>
                  <button className="dropdown-item" style={{ display: "block", width: "100%", padding: "8px 12px", background: "none", border: "none", color: "#fafafa", textAlign: "left", cursor: "pointer", fontSize: 14 }} onClick={() => { setDropdownOpen(false); handleExportPDF(); }}>PDF Report</button>
                  <button className="dropdown-item" style={{ display: "block", width: "100%", padding: "8px 12px", background: "none", border: "none", color: "#fafafa", textAlign: "left", cursor: "pointer", fontSize: 14 }} onClick={() => { setDropdownOpen(false); void downloadArtifact(sessionId, 'transcript'); }}>Transcript (.json)</button>
                </div>
              )}
            </div>
            <button className="btn btn-ghost" onClick={onDone}>New interview</button>
          </div>
        </div>
      </nav>

      <div ref={captureRef}>
        <main className="container">
          {/* Page head */}
          <header className="page-head">
            <div>
              <span className="page-eyebrow">
                <span className="lit">Interview Report</span>
                <span>·</span>
                <span>{generatedDate}</span>
              </span>
              <h1 className="page-h1">Interview <em>Result</em></h1>
            </div>
            <div className="page-head-actions">
              <div className="dropdown" style={{ position: "relative" }}>
                <button className="btn btn-ghost" type="button" onClick={() => setDropdownOpen(!dropdownOpen)} disabled={exporting}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  {exporting ? "Exporting…" : "Download"}
                </button>
                {dropdownOpen && (
                  <div className="dropdown-menu" style={{ position: "absolute", right: 0, top: "100%", marginTop: 4, background: "#1c1c22", border: "1px solid #27272a", borderRadius: 8, padding: "4px 0", zIndex: 50, minWidth: 160 }}>
                    <button className="dropdown-item" style={{ display: "block", width: "100%", padding: "8px 12px", background: "none", border: "none", color: "#fafafa", textAlign: "left", cursor: "pointer", fontSize: 14 }} onClick={() => { setDropdownOpen(false); handleExportPDF(); }}>PDF Report</button>
                    <button className="dropdown-item" style={{ display: "block", width: "100%", padding: "8px 12px", background: "none", border: "none", color: "#fafafa", textAlign: "left", cursor: "pointer", fontSize: 14 }} onClick={() => { setDropdownOpen(false); void downloadArtifact(sessionId, 'transcript'); }}>Transcript (.json)</button>
                  </div>
                )}
              </div>
            </div>
          </header>

          {/* Hero: candidate identity + score ring */}
          <section className="hero" aria-label="Candidate summary">
            <article className="card glow card-pad">
              <div className="candidate-head">
                <div className="avatar" aria-hidden="true">{initials}</div>
                <div className="candidate-id">
                  <h2 className="candidate-name">{report.candidate_name}</h2>
                  <div className="candidate-role">Candidate · Voice interview · Aura</div>
                </div>
              </div>

              <div className="meta-row" aria-label="Interview metadata">
                <div className="meta-cell">
                  <div className="meta-label">Date</div>
                  <div className="meta-value">{generatedDate}</div>
                </div>
                <div className="meta-cell">
                  <div className="meta-label">Modality</div>
                  <div className="meta-value">Voice · WSS</div>
                </div>
                <div className="meta-cell">
                  <div className="meta-label">Agent</div>
                  <div className="meta-value">Aura · en-US</div>
                </div>
              </div>

              <div className="summary-block">
                <div className="summary-eyebrow">Overall performance summary</div>
                <p>{report.summary}</p>
              </div>
            </article>

            <article className="card glow score-card">
              <div className="score-card-head">
                <h3>Overall Score</h3>
                <span className={rec.cls}><span className="dot"></span>{rec.text}</span>
              </div>

              <div className="score-ring-wrap" aria-hidden="true">
                <div className="score-ring" style={{ ['--p' as any]: overallPct }}></div>
                <div className="score-center">
                  <div className="score-num">{report.overall_score}<span className="denom">/100</span></div>
                  <div className="score-band">{rec.text}</div>
                </div>
              </div>
            </article>
          </section>

          {/* Strengths / Areas for improvement */}
          <section className="section" aria-label="Strengths and watch-outs">
            <div className="two-col">
              <article className="card card-pad-tight">
                <div className="insight-head s">
                  <span className="icon-pip" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  </span>
                  <h3>Key strengths</h3>
                </div>
                <ul className="insight-list">
                  {report.strengths.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </article>

              <article className="card card-pad-tight">
                <div className="insight-head w">
                  <span className="icon-pip" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="9"/>
                      <line x1="12" y1="8" x2="12" y2="12"/>
                      <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                  </span>
                  <h3>Areas for improvement</h3>
                </div>
                <ul className="insight-list">
                  {report.weaknesses.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </article>
            </div>
          </section>

          {/* Section breakdown */}
          <section className="section" aria-label="Section breakdown">
            <div className="section-head">
              <h2 className="section-title">Section breakdown</h2>
              <span className="section-sub">{report.section_grades.length} dimensions</span>
            </div>

            <article className="card">
              <div className="rubric">
                {report.section_grades.map((g, i) => {
                  const pct = Math.max(0, Math.min(100, g.score * 10));
                  return (
                    <div key={i} className="rubric-row">
                      <div className="rubric-name">
                        <span className="n">{g.section_name}</span>
                      </div>
                      <p className="rubric-evidence">{g.comments}</p>
                      <div className="rubric-meter">
                        <div className="rubric-meter-head">
                          <span className="score">{g.score}<span className="denom"> / 10</span></span>
                        </div>
                        <div className="meter" aria-hidden="true">
                          <i style={{ ['--w' as any]: `${pct}%` }}></i>
                        </div>
                        <div className="meter-foot">
                          <span>0</span><span>10</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </article>
          </section>

          {/* Action bar */}
          <section className="action-bar" aria-label="Decision actions">
            <div className="action-meta">
              <span>Generated by Aura</span>
              <span className="sep"></span>
              <span>{generatedDate}</span>
            </div>
            <div className="action-set">
              <button className="btn btn-ghost" type="button" onClick={onDone}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="19" y1="12" x2="5" y2="12"/>
                  <polyline points="12 19 5 12 12 5"/>
                </svg>
                Back to Aura
              </button>
              <div className="dropdown" style={{ position: "relative" }}>
                <button className="btn btn-primary" type="button" onClick={() => setDropdownOpen(!dropdownOpen)} disabled={exporting}>
                  {exporting ? "Exporting…" : "Download"}
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
                {dropdownOpen && (
                  <div className="dropdown-menu" style={{ position: "absolute", right: 0, bottom: "100%", marginBottom: 4, background: "#1c1c22", border: "1px solid #27272a", borderRadius: 8, padding: "4px 0", zIndex: 50, minWidth: 160 }}>
                    <button className="dropdown-item" style={{ display: "block", width: "100%", padding: "8px 12px", background: "none", border: "none", color: "#fafafa", textAlign: "left", cursor: "pointer", fontSize: 14 }} onClick={() => { setDropdownOpen(false); handleExportPDF(); }}>PDF Report</button>
                    <button className="dropdown-item" style={{ display: "block", width: "100%", padding: "8px 12px", background: "none", border: "none", color: "#fafafa", textAlign: "left", cursor: "pointer", fontSize: 14 }} onClick={() => { setDropdownOpen(false); void downloadArtifact(sessionId, 'transcript'); }}>Transcript (.json)</button>
                  </div>
                )}
              </div>
            </div>
          </section>

          <footer className="page-foot">
            <span>© 2026 Aura · Built on LiveKit &amp; Pydantic AI</span>
            <span><Link to="/">Landing</Link></span>
          </footer>
        </main>
      </div>
    </div>
  );
}
