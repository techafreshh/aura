import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  useLocalParticipant,
  useRoomContext,
  useTranscriptions,
  useConnectionState,
  useMediaDeviceSelect,
  useTrackVolume,
  useMultibandTrackVolume,
} from "@livekit/components-react";
import { useState, useEffect, useRef } from "react";
import { Track, ConnectionState, type LocalAudioTrack } from "livekit-client";
import axios from "axios";
import { getReport, uploadAudio } from "@/api/client";
import { useRoomRecorder } from "@/hooks/use-recorder";
import { useInterviewGuard } from "@/hooks/use-interview-guard";
import { useToast } from "@/hooks/use-toast";
import "@/styles/aura-arena.css";

interface InterviewAgentProps {
  token: string;
  sessionId: string;
  candidateName?: string;
  /** Record mic + agent audio in the browser and upload on end (recruiter invites). */
  recordAudio?: boolean;
  onInterviewEnd: (report: any) => void;
}

const ARC_COUNT = 28;
const METER_BARS = 28;
const DUST_COUNT = 14;

/** Compact mic selector that fits in the topbar. */
function MicSelector() {
  const { devices, activeDeviceId, setActiveMediaDevice } = useMediaDeviceSelect({ kind: "audioinput", requestPermissions: true });
  const [open, setOpen] = useState(false);
  const filtered = devices.filter((d) => d.deviceId !== "");
  const active = filtered.find((d) => d.deviceId === activeDeviceId);
  const label = active?.label || "Mic";

  if (filtered.length === 0) return null;

  return (
    <div className="mic-select" onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        className="mic-select-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        title={label}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="3" width="6" height="12" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0" />
          <path d="M12 18v3" />
        </svg>
        <span className="mic-name">{label.length > 18 ? label.slice(0, 16) + "…" : label}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <ul role="listbox" className="mic-menu">
          {filtered.map((d) => (
            <li
              key={d.deviceId}
              role="option"
              aria-selected={d.deviceId === activeDeviceId}
              className={d.deviceId === activeDeviceId ? "selected" : ""}
              onClick={() => {
                setActiveMediaDevice(d.deviceId);
                setOpen(false);
              }}
            >
              {d.label || `Mic (${d.deviceId.slice(0, 8)})`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function InterviewInner({ sessionId, candidateName = "Candidate", recordAudio = false, onInterviewEnd }: { sessionId: string; candidateName?: string; recordAudio?: boolean; onInterviewEnd: (report: any) => void }) {
  const { toast } = useToast();
  const [hasConnected, setHasConnected] = useState(false);
  const [hasEnded, setHasEnded] = useState(false);
  const [endedOpen, setEndedOpen] = useState(false);
  const [muted, setMuted] = useState(false);
  const TOTAL_SECONDS = 10 * 60;
  const WARNING_SECONDS = 2 * 60;
  const [remaining, setRemaining] = useState(TOTAL_SECONDS);
  const [transcriptWidth, setTranscriptWidth] = useState(420);

  const roomState = useConnectionState();
  const room = useRoomContext();
  const { state: agentState, audioTrack: agentAudioTrack } = useVoiceAssistant();
  const { localParticipant } = useLocalParticipant();
  const transcriptions = useTranscriptions();

  // Local mic track reference (for volume hooks)
  const micPub = localParticipant?.getTrackPublication(Track.Source.Microphone);
  const micTrack = (micPub?.track as LocalAudioTrack | undefined) ?? undefined;

  // Audio level hooks - real-time from LiveKit
  const userBands = useMultibandTrackVolume(micTrack, { bands: METER_BARS, updateInterval: 50 });
  const userArcs = useMultibandTrackVolume(micTrack, { bands: ARC_COUNT, updateInterval: 50 });
  const agentVolume = useTrackVolume(agentAudioTrack?.publication?.track as any);

  // Browser-side recording (recruiter invite sessions only). The upload runs
  // from onstop rather than a state-watching effect: MediaRecorder fires onstop
  // asynchronously, so reacting to a render would read the blob before it exists.
  const audioUploadedRef = useRef(false);
  const handleRecordingComplete = (recorded: Blob) => {
    if (audioUploadedRef.current || recorded.size === 0) return;
    audioUploadedRef.current = true;
    const ext = recorded.type.includes("mp4") ? "mp4" : "webm";
    uploadAudio(sessionId, recorded, ext).catch((err) => {
      // Allow a later stop to retry rather than dropping the recording.
      audioUploadedRef.current = false;
      console.error("Audio upload failed:", err);
      // The recruiter sees only "no recording available" otherwise — make the
      // failure visible to the candidate so it can be reported/retried.
      toast({
        title: "Recording not saved",
        description: "We couldn't upload the interview recording. The report is unaffected — please mention it to your recruiter.",
        variant: "destructive",
        duration: 8000,
      });
    });
  };

  const { recording, stop: stopRecorder } = useRoomRecorder({
    enabled: recordAudio,
    connected: roomState === ConnectionState.Connected,
    micTrack: micTrack as unknown as Parameters<typeof useRoomRecorder>[0]["micTrack"],
    agentTrack: agentAudioTrack as unknown as Parameters<typeof useRoomRecorder>[0]["agentTrack"],
    onComplete: handleRecordingComplete,
  });

  // Refs
  const orbWrapRef = useRef<HTMLDivElement>(null);
  const arcGroupRef = useRef<SVGGElement>(null);
  const dustRef = useRef<HTMLDivElement>(null);
  const meterRef = useRef<HTMLDivElement>(null);
  const transcriptBodyRef = useRef<HTMLDivElement>(null);
  const transcriptRef = useRef<HTMLElement>(null);
  const arcsRef = useRef<SVGCircleElement[]>([]);
  const barsRef = useRef<HTMLSpanElement[]>([]);

  // Map agent state -> design data-state
  const orbState: "idle" | "listening" | "thinking" | "speaking" =
    agentState === "speaking" ? "speaking"
    : agentState === "thinking" ? "thinking"
    : agentState === "listening" ? "listening"
    : "idle";

  // Build voice arc segments once
  useEffect(() => {
    const g = arcGroupRef.current;
    if (!g) return;
    const cx = 100, cy = 100, rOuter = 96;
    const els: SVGCircleElement[] = [];
    for (let i = 0; i < ARC_COUNT; i++) {
      const seg = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      seg.setAttribute("cx", String(cx));
      seg.setAttribute("cy", String(cy));
      seg.setAttribute("r", String(rOuter));
      seg.setAttribute("stroke-dasharray", "2 600");
      seg.setAttribute("stroke-dashoffset", String(-(i / ARC_COUNT) * 2 * Math.PI * rOuter));
      seg.setAttribute("stroke-linecap", "round");
      seg.setAttribute("stroke-width", "2");
      seg.setAttribute("opacity", "0.6");
      g.appendChild(seg);
      els.push(seg);
    }
    arcsRef.current = els;
    return () => { els.forEach((e) => e.remove()); arcsRef.current = []; };
  }, []);

  // Build dust particles once
  useEffect(() => {
    const dust = dustRef.current;
    if (!dust) return;
    const created: HTMLSpanElement[] = [];
    for (let i = 0; i < DUST_COUNT; i++) {
      const s = document.createElement("span");
      const ang = Math.random() * Math.PI * 2;
      const r = 30 + Math.random() * 20;
      s.style.left = `${50 + Math.cos(ang) * r}%`;
      s.style.top = `${50 + Math.sin(ang) * r}%`;
      s.style.animationDelay = `${-Math.random() * 9}s`;
      s.style.animationDuration = `${7 + Math.random() * 6}s`;
      s.style.opacity = (0.4 + Math.random() * 0.6).toFixed(2);
      s.style.setProperty("--dx", `${(Math.random() * 14 - 7).toFixed(1)}px`);
      s.style.setProperty("--dy", `${(Math.random() * 14 - 7).toFixed(1)}px`);
      dust.appendChild(s);
      created.push(s);
    }
    return () => { created.forEach((e) => e.remove()); };
  }, []);

  // Build meter bars once
  useEffect(() => {
    const meter = meterRef.current;
    if (!meter) return;
    const created: HTMLSpanElement[] = [];
    for (let i = 0; i < METER_BARS; i++) {
      const b = document.createElement("span");
      b.className = "bar";
      meter.appendChild(b);
      created.push(b);
    }
    barsRef.current = created;
    return () => { created.forEach((e) => e.remove()); barsRef.current = []; };
  }, []);

  // Drive meter bars from real user mic frequency bands
  useEffect(() => {
    const bars = barsRef.current;
    if (!bars.length) return;
    for (let i = 0; i < bars.length; i++) {
      const v = muted ? 0 : (userBands[i] ?? 0);
      const h = Math.max(4, Math.min(28, 4 + v * 60));
      bars[i].style.height = `${h.toFixed(1)}px`;
      bars[i].style.opacity = muted ? "0.25" : `${(0.4 + v * 0.7).toFixed(2)}`;
    }
  }, [userBands, muted]);

  // Drive voice arcs from real user mic frequency bands (visible only during listening)
  useEffect(() => {
    const arcs = arcsRef.current;
    if (!arcs.length) return;
    const visible = orbState === "listening" && !muted;
    for (let i = 0; i < arcs.length; i++) {
      if (!visible) {
        arcs[i].setAttribute("opacity", "0");
        continue;
      }
      const v = userArcs[i] ?? 0;
      arcs[i].setAttribute("stroke-width", (1.4 + v * 6).toFixed(2));
      arcs[i].setAttribute("opacity", (0.3 + v * 0.7).toFixed(2));
    }
  }, [userArcs, orbState, muted]);

  // Drive orb pulse from real agent audio volume
  useEffect(() => {
    const orb = orbWrapRef.current;
    if (!orb) return;
    // Smooth value to avoid jitter
    const v = Math.max(0, Math.min(1, agentVolume));
    orb.style.setProperty("--agent-vol", v.toFixed(3));
  }, [agentVolume]);

  // Build transcript messages from real LiveKit data
  const localMicTrackSid = micPub?.trackSid;
  const rawMessages = transcriptions.map((t: any, idx: number) => {
    const tid = t.streamInfo?.attributes?.["lk.transcribed_track_id"];
    return { id: t.streamInfo?.id || `msg-${idx}`, message: t.text || "", isLocal: tid === localMicTrackSid };
  }).filter((m) => m.message);
  const messages = rawMessages.reduce<typeof rawMessages>((acc, msg) => {
    const last = acc[acc.length - 1];
    if (last && last.isLocal === msg.isLocal) last.message += " " + msg.message;
    else acc.push({ ...msg });
    return acc;
  }, []);

  // Auto-scroll transcript on new message
  useEffect(() => {
    const body = transcriptBodyRef.current;
    if (body) body.scrollTop = body.scrollHeight;
  }, [messages.length]);

  // Track connection
  useEffect(() => {
    if (roomState === ConnectionState.Connected) setHasConnected(true);
  }, [roomState]);

  // Stop the recorder when the room disconnects; the finished blob is uploaded
  // from the recorder's onstop callback (see the hook call above), which fires
  // asynchronously — so nothing here waits on a render to notice it.
  useEffect(() => {
    if (recordAudio && roomState === ConnectionState.Disconnected) {
      stopRecorder();
    }
  }, [roomState, recordAudio, stopRecorder]);

  // Timer
  useEffect(() => {
    if (!hasConnected) return;
    const i = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(i);
  }, [hasConnected]);
  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");
  const isWarning = remaining <= WARNING_SECONDS && remaining > 0;
  const isCritical = remaining <= 30 && remaining > 0;

  // Mute toggle
  const toggleMute = async () => {
    if (!micTrack) return;
    if (muted) await micTrack.unmute();
    else await micTrack.mute();
    setMuted(!muted);
  };

  // End interview — disconnect the room so the worker generates the report and shuts down
  const endInterview = async () => {
    setEndedOpen(true);
    setHasEnded(true);
    try { await localParticipant?.setMicrophoneEnabled(false); } catch {}
    try { await room?.disconnect(); } catch (e) { console.error("Room disconnect failed:", e); }
  };

  // Leave guard — active only while the room is live and the user hasn't
  // already ended the session, so previewing and the end-of-interview teardown
  // stay friction-free. A confirmed leave runs endInterview: the worker
  // finalizes the report and the ended-overlay poll below picks it up.
  const { confirmOpen: leaveConfirmOpen, requestLeave, resolveLeave } = useInterviewGuard(
    roomState === ConnectionState.Connected && !hasEnded,
    endInterview,
  );

  // Escape closes the guard modal; the safe action ("Stay") gets focus so
  // Enter is also the non-destructive choice.
  const stayButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!leaveConfirmOpen) return;
    stayButtonRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") resolveLeave(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [leaveConfirmOpen, resolveLeave]);

  // After end, poll for the report via the authed axios client — the previous
  // EventSource transport couldn't send the JWT and never received a report.
  // A 404 just means the worker hasn't finished generating the report yet.
  const [reportError, setReportError] = useState<string | null>(null);
  useEffect(() => {
    if (hasConnected && roomState === ConnectionState.Disconnected && !hasEnded) {
      setHasEnded(true);
      setEndedOpen(true);
    }

    if (hasEnded && endedOpen) {
      let cancelled = false;
      const startedAt = Date.now();
      const POLL_INTERVAL_MS = 3000;
      const TIMEOUT_MS = 120_000;

      const poll = async () => {
        while (!cancelled) {
          try {
            const report = await getReport(sessionId);
            if (!cancelled) onInterviewEnd(report);
            return;
          } catch (error) {
            if (cancelled) return;
            const status = axios.isAxiosError(error) ? error.response?.status : undefined;
            // 404 = report not generated yet (expected while it renders);
            // 401/403 = auth problem that retrying cannot fix; network errors
            // and 5xx/429 are transient and worth retrying until the deadline.
            const isPending = status === 404;
            const isFatal = status === 401 || status === 403;
            if (isFatal || Date.now() - startedAt >= TIMEOUT_MS) {
              if (isPending) {
                setReportError("Report generation timed out. The interview may have been too short for a meaningful report.");
              } else if (isFatal) {
                setReportError("You are not authorized to view this report.");
              } else {
                setReportError("Connection lost. Please try again.");
              }
              return;
            }
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          }
        }
      };
      poll();
      return () => {
        cancelled = true;
      };
    }
  }, [roomState, hasConnected, hasEnded, endedOpen, sessionId, onInterviewEnd]);

  // Resizable transcript handle
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);
  const onDragStart = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startW: transcriptWidth };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onDragMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    const dx = dragRef.current.startX - e.clientX; // dragging left = wider
    const next = Math.max(280, Math.min(720, dragRef.current.startW + dx));
    setTranscriptWidth(next);
  };
  const onDragEnd = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    try { (e.target as HTMLElement).releasePointerCapture(e.pointerId); } catch {}
  };

  const stateLabel = orbState === "idle" ? "Idle" : orbState === "listening" ? "Listening" : orbState === "thinking" ? "Processing" : "Speaking";
  const initials = candidateName.split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase() || "C";
  const sidShort = sessionId.slice(0, 4) + "-" + sessionId.slice(-4);

  return (
    <div className="aura-arena-page">
      <div className="ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      {/* Top status bar */}
      <header className="topbar" role="banner">
        <div className="top-left">
          <a
            className="brand"
            href="/"
            aria-label="Aura — back to home"
            onClick={(e) => {
              if (roomState === ConnectionState.Connected && !hasEnded) {
                e.preventDefault();
                requestLeave();
              }
            }}
          >
            <span className="mark" aria-hidden="true"></span>
            <span className="text">Aura</span>
          </a>
          <div className="candidate-chip" aria-label="Candidate">
            <span className="avatar" aria-hidden="true">{initials}</span>
            <span className="name">{candidateName}</span>
          </div>
        </div>

        <div className="top-center">
          <div className="session-status" aria-live="polite" aria-atomic="true" data-recording={recording ? "true" : "false"}>
            <span className="rec-dot" aria-hidden="true"></span>
            <span>{recording ? "Recording" : "Session · Active"}</span>
          </div>
        </div>

        <div className="top-right">
          <MicSelector />
          <div className={`timer ${isWarning ? 'timer-warning' : ''} ${isCritical ? 'timer-critical' : ''}`}
               aria-label={`${mm}:${ss} remaining`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            <span>{mm}:{ss}</span>
          </div>
          <div className="session-id" aria-label="Session identifier">
            <strong>SID</strong> · {sidShort}
          </div>
        </div>
      </header>

      {/* Stage */}
      <main className="stage" style={{ gridTemplateColumns: `1fr ${transcriptWidth}px` }}>
        <section className="orb-zone" aria-label="Aura agent presence">
          <div
            className="orb-wrap"
            ref={orbWrapRef}
            data-state={orbState}
            data-muted={muted ? "true" : "false"}
          >
            <div className="orb-glow" aria-hidden="true"></div>
            <div className="orb-ring-set" aria-hidden="true">
              <span className="orb-ring r1"></span>
              <span className="orb-ring r2"></span>
              <span className="orb-ring r3"></span>
              <span className="orb-ring r4"></span>
            </div>

            <svg className="voice-arcs" viewBox="0 0 200 200" aria-hidden="true">
              <defs>
                <linearGradient id="arcGrad" x1="0" x2="1" y1="0" y2="1">
                  <stop offset="0%" stopColor="#a5b4fc" stopOpacity="0.9" />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity="0.4" />
                </linearGradient>
              </defs>
              <g ref={arcGroupRef} stroke="url(#arcGrad)"></g>
            </svg>

            <div className="pulse-rings" aria-hidden="true">
              <span></span><span></span><span></span><span></span>
            </div>

            <div className="orb-dust" ref={dustRef} aria-hidden="true"></div>
            <div className="orb-core" aria-hidden="true"></div>
          </div>

          <div className="state-plate">
            <span className="pip" aria-hidden="true"></span>
            <span>{stateLabel}</span>
          </div>
        </section>

        {/* Transcript with resize handle */}
        <aside className="transcript" ref={transcriptRef} aria-label="Live transcript" style={{ width: "auto" }}>
          <div
            className="transcript-resize"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize transcript"
            onPointerDown={onDragStart}
            onPointerMove={onDragMove}
            onPointerUp={onDragEnd}
            onPointerCancel={onDragEnd}
          />
          <div className="transcript-header">
            <div className="transcript-title">
              <span className="live-pip" aria-hidden="true"></span>
              <span>Live transcript</span>
            </div>
            <div className="transcript-meta">EN · auto</div>
          </div>
          <div className="transcript-body" ref={transcriptBodyRef} aria-live="polite">
            {messages.length === 0 && (
              <div style={{ color: "var(--muted-2)", fontSize: 13, textAlign: "center", marginTop: 24, fontStyle: "italic" }}>
                Waiting for conversation…
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.isLocal ? "user" : "aura"}`}>
                <div className="who" aria-hidden="true">{m.isLocal ? "Y" : "A"}</div>
                <div className="body">
                  <div className="head">
                    <span className="name">{m.isLocal ? "You" : "Aura"}</span>
                  </div>
                  <div className="text">{m.message}</div>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </main>

      {/* Bottom action dock */}
      <div className="dock-wrap">
        <p className="dock-note" aria-hidden="true">
          Don't refresh or close this tab — the interview ends and the session's credits are used.
        </p>
        <div className="dock" role="toolbar" aria-label="Interview controls">
          <button
            className={`dock-btn ${muted ? "muted" : ""}`}
            onClick={toggleMute}
            aria-pressed={muted}
            aria-label={muted ? "Unmute microphone" : "Mute microphone"}
            type="button"
          >
            <svg className="ico ico-mic-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="9" y="3" width="6" height="12" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0" />
              <path d="M12 18v3" />
            </svg>
            <svg className="ico ico-mic-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 3l18 18" />
              <path d="M9 9v3a3 3 0 0 0 4.83 2.36" />
              <path d="M15 12V6a3 3 0 0 0-5.94-.6" />
              <path d="M5 11a7 7 0 0 0 11.28 5.6" />
              <path d="M19 11a7 7 0 0 1-.4 2.34" />
              <path d="M12 18v3" />
            </svg>
            <span className="label">{muted ? "Unmute" : "Mute"}</span>
          </button>

          <div className="meter" ref={meterRef} data-muted={muted ? "true" : "false"} aria-hidden="true"></div>

          <button className="dock-btn danger" onClick={endInterview} aria-label="End interview" type="button">
            <svg className="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3.5 14.5a3 3 0 0 1 0-5L4 9a17 17 0 0 1 16 0l.5.5a3 3 0 0 1 0 5l-2 .8a2 2 0 0 1-2.4-.7l-1-1.4a2 2 0 0 0-1.6-.9h-2a2 2 0 0 0-1.6.9l-1 1.4a2 2 0 0 1-2.4.7Z" />
            </svg>
            <span className="label">End interview</span>
          </button>
        </div>
      </div>

      {/* Ended overlay */}
      <div className="ended-overlay" data-open={endedOpen ? "true" : "false"} role="status" aria-live="polite">
        <div>
          <div className="check" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2>{reportError ? "Report unavailable" : "Interview complete"}</h2>
          <p>{reportError ?? "Generating the candidate report — this typically takes a few seconds."}</p>
          {reportError && (
            <button className="btn btn-ghost" type="button" onClick={() => window.location.assign("/interview")} style={{ marginTop: 16 }}>
              Start over
            </button>
          )}
        </div>
      </div>

      {/* Leave-intent modal — refreshing or navigating away mid-interview
          disconnects the room, finalizes the report, and spends the session. */}
      <div
        className="guard-overlay"
        data-open={leaveConfirmOpen ? "true" : "false"}
        role="presentation"
        onClick={() => resolveLeave(false)}
      >
        <div
          className="guard-modal"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="guard-title"
          aria-describedby="guard-desc"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="guard-icon" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>
          <h2 id="guard-title">Leave the interview?</h2>
          <p id="guard-desc">
            Refreshing, closing this tab, or navigating away ends the interview now.
            The report is generated from what's been said so far, and this session's
            credits are spent either way.
          </p>
          <div className="guard-actions">
            <button ref={stayButtonRef} className="btn btn-ghost" type="button" onClick={() => resolveLeave(false)}>
              Stay in interview
            </button>
            <button className="btn btn-danger" type="button" onClick={() => resolveLeave(true)}>
              End &amp; leave
            </button>
          </div>
        </div>
      </div>

      <RoomAudioRenderer />
    </div>
  );
}

export function InterviewAgent({ token, sessionId, candidateName, recordAudio, onInterviewEnd }: InterviewAgentProps) {
  const serverUrl = import.meta.env.VITE_LIVEKIT_URL;
  if (!serverUrl) return <div style={{ padding: 32, textAlign: "center", color: "#ef4444" }}>VITE_LIVEKIT_URL is missing in .env</div>;
  return (
    <LiveKitRoom serverUrl={serverUrl} token={token} connect={true} audio={true} video={false} onError={(err) => console.error("LiveKit Error:", err)}>
      <InterviewInner sessionId={sessionId} candidateName={candidateName} recordAudio={recordAudio} onInterviewEnd={onInterviewEnd} />
    </LiveKitRoom>
  );
}
