import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, cleanup } from '@testing-library/react'
import { useRoomRecorder } from '../use-recorder'

/**
 * Regression coverage for the recorder hand-off.
 *
 * MediaRecorder fires ``onstop`` asynchronously, so the finished blob must be
 * delivered from that callback. The original implementation exposed a ref that
 * consumers read inside a React effect keyed on the connection state: the effect
 * ran in the same commit as the stop (before ``onstop``) and, because a ref write
 * triggers no re-render, it never ran again — so the recording was never
 * uploaded. These tests fail if the hook goes back to ref-only delivery.
 */

const MIC = { mediaStreamTrack: { id: 'mic' } as unknown as MediaStreamTrack }
const AGENT = { mediaStreamTrack: { id: 'agent' } as unknown as MediaStreamTrack }

class FakeAudioContext {
  createMediaStreamDestination() {
    return { stream: { id: 'mixed-destination' } }
  }
  createMediaStreamSource() {
    return { connect() {} }
  }
  close() {
    return Promise.resolve()
  }
}

class FakeMediaRecorder {
  static isTypeSupported = () => true

  state = 'inactive'
  mimeType = 'audio/webm;codecs=opus'
  stream: unknown
  options: unknown
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null

  constructor(stream: unknown, options?: unknown) {
    this.stream = stream
    this.options = options
  }

  start() {
    this.state = 'recording'
  }

  stop() {
    this.state = 'inactive'
    // Mirrors the real ordering: dataavailable, then stop, both asynchronously.
    setTimeout(() => {
      this.ondataavailable?.({ data: new Blob(['interview-audio'], { type: 'audio/webm' }) })
      this.onstop?.()
    }, 0)
  }
}

function Harness({ connected, onComplete }: { connected: boolean; onComplete: (b: Blob) => void }) {
  const { recording, blob, stop } = useRoomRecorder({
    enabled: true,
    connected,
    micTrack: MIC,
    agentTrack: AGENT,
    onComplete,
  })
  return (
    <div>
      <span data-testid="recording">{String(recording)}</span>
      <span data-testid="blob-size">{blob?.size ?? 0}</span>
      <button onClick={stop}>stop</button>
    </div>
  )
}

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 10)) })

describe('useRoomRecorder', () => {
  beforeEach(() => {
    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('starts recording once connected with both tracks available', async () => {
    const { getByTestId } = render(<Harness connected={true} onComplete={() => {}} />)
    await flush()
    expect(getByTestId('recording').textContent).toBe('true')
  })

  it('does not start until the agent track is present', async () => {
    const { getByTestId } = render(<Harness connected={false} onComplete={() => {}} />)
    await flush()
    expect(getByTestId('recording').textContent).toBe('false')
  })

  it('delivers the finished recording to onComplete when stopped', async () => {
    const onComplete = vi.fn()
    const { getByText, getByTestId } = render(<Harness connected={true} onComplete={onComplete} />)
    await flush()

    act(() => { getByText('stop').click() })
    await flush()

    expect(onComplete).toHaveBeenCalledTimes(1)
    const delivered = onComplete.mock.calls[0][0] as Blob
    expect(delivered).toBeInstanceOf(Blob)
    expect(delivered.size).toBeGreaterThan(0)
    // Also exposed as state for consumers that render it.
    expect(Number(getByTestId('blob-size').textContent)).toBeGreaterThan(0)
  })

  it('still delivers the recording when the component unmounts mid-interview', async () => {
    const onComplete = vi.fn()
    const { unmount, getByTestId } = render(<Harness connected={true} onComplete={onComplete} />)
    await flush()
    expect(getByTestId('recording').textContent).toBe('true')

    // Navigating away stops the recorder, but no further render ever happens —
    // a ref-based hand-off would drop the audio here.
    unmount()
    await flush()

    expect(onComplete).toHaveBeenCalledTimes(1)
    expect((onComplete.mock.calls[0][0] as Blob).size).toBeGreaterThan(0)
  })
})
