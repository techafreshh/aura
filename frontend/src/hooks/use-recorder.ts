import { useCallback, useEffect, useRef, useState } from 'react'

interface RecorderTrack {
  mediaStreamTrack?: MediaStreamTrack | null
  publication?: { track?: { mediaStreamTrack?: MediaStreamTrack | null } } | null
}

interface UseRoomRecorderArgs {
  /** Recording is only enabled for invited interviews. */
  enabled: boolean
  /** LiveKit connection state — recording starts once connected. */
  connected: boolean
  /** Local participant's mic track (from useLocalParticipant). */
  micTrack?: RecorderTrack | null
  /** Agent's remote audio track (from useVoiceAssistant). */
  agentTrack?: RecorderTrack | null
}

interface UseRoomRecorderResult {
  recording: boolean
  /** The completed recording, set once the recorder stops. */
  blobRef: React.MutableRefObject<Blob | null>
  stop: () => void
}

function extractMediaTrack(track: RecorderTrack | null | undefined): MediaStreamTrack | null {
  if (!track) return null
  // LiveKit LocalAudioTrack / RemoteAudioTrack expose .mediaStreamTrack
  if (track.mediaStreamTrack) return track.mediaStreamTrack
  if (track.publication?.track?.mediaStreamTrack) return track.publication.track.mediaStreamTrack
  return null
}

/**
 * Browser-side interview recorder.
 *
 * Mixes the candidate's mic and the AI interviewer's voice into a single
 * stream via Web Audio and captures it with MediaRecorder — zero per-minute
 * recording cost, unlike LiveKit Egress. The blob is produced on stop();
 * callers upload it (see InterviewAgent).
 */
export function useRoomRecorder({ enabled, connected, micTrack, agentTrack }: UseRoomRecorderArgs): UseRoomRecorderResult {
  const recorderRef = useRef<MediaRecorder | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const blobRef = useRef<Blob | null>(null)
  const startedRef = useRef(false)
  const [recording, setRecording] = useState(false)

  useEffect(() => {
    if (!enabled || !connected || startedRef.current) return

    // Wait for the agent's audio track so both voices are captured — the effect
    // re-runs on track identity changes, so this resolves as soon as it exists.
    const mic = extractMediaTrack(micTrack)
    const agent = extractMediaTrack(agentTrack)
    if (!mic || !agent) return
    startedRef.current = true

    try {
      const ctx = new AudioContext()
      const dest = ctx.createMediaStreamDestination()
      for (const t of [mic, agent]) {
        try { ctx.createMediaStreamSource(new MediaStream([t])).connect(dest) } catch { /* track gone */ }
      }
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4' : ''
      const recorder = new MediaRecorder(dest.stream, mime ? { mimeType: mime } : undefined)
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      recorder.onstop = () => {
        blobRef.current = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
      }
      recorder.start(1000)
      audioCtxRef.current = ctx
      recorderRef.current = recorder
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRecording(true)
    } catch (err) {
      console.error('Interview recorder failed to start:', err)
      startedRef.current = false
    }
  }, [enabled, connected, micTrack, agentTrack])

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {})
      audioCtxRef.current = null
    }
    setRecording(false)
  }, [])

  // Safety net: stop everything on unmount
  useEffect(() => () => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      try { recorderRef.current.stop() } catch { /* already stopped */ }
    }
    audioCtxRef.current?.close().catch(() => {})
  }, [])

  return { recording, blobRef, stop }
}
