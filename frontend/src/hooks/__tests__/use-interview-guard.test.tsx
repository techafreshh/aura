import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, act, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useInterviewGuard } from '../use-interview-guard'

/**
 * The guard combines two exits with different browser mechanics: the native
 * beforeunload dialog for refresh/close, and a history sentinel whose popstate
 * opens the in-app modal for Back presses. These tests pin both halves: the
 * sentinel must re-arm after every Stay (otherwise the second Back leaves
 * silently) and must stop intercepting once the user confirms leaving,
 * otherwise the report-generation overlay could never be navigated away from.
 */

function Harness({ enabled, onConfirm }: { enabled: boolean; onConfirm: () => void }) {
  const { confirmOpen, resolveLeave } = useInterviewGuard(enabled, onConfirm)
  return (
    <div data-testid="modal" data-open={confirmOpen ? 'true' : 'false'}>
      <button data-testid="stay" onClick={() => resolveLeave(false)}>stay</button>
      <button data-testid="leave" onClick={() => resolveLeave(true)}>leave</button>
    </div>
  )
}

const isOpen = () => screen.getByTestId('modal').dataset.open === 'true'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('useInterviewGuard', () => {
  it('does nothing while disabled', () => {
    render(<Harness enabled={false} onConfirm={() => {}} />)
    act(() => {
      window.dispatchEvent(new Event('popstate'))
    })
    expect(isOpen()).toBe(false)
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
  })

  it('asks the browser to confirm refresh/close while enabled', () => {
    render(<Harness enabled onConfirm={() => {}} />)
    const event = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent
    // jsdom's returnValue getter collapses to `false` once the event is
    // canceled, so observe the assignment instead — that string is what
    // Firefox/Safari render in the dialog.
    let assigned: string | undefined
    Object.defineProperty(event, 'returnValue', {
      set(v: string) { assigned = v },
      get() { return assigned ?? false },
    })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(assigned).toContain('credits')
  })

  it('opens the modal on a back press without leaving the page', async () => {
    render(<Harness enabled onConfirm={() => {}} />)
    await act(async () => {
      window.history.back()
    })
    await waitFor(() => expect(isOpen()).toBe(true))
    // The sentinel shares the interview URL, so popping it changes nothing
    // visible — React Router (and the interview) stay mounted.
    expect(window.location.pathname).toBe('/')
  })

  it('re-arms after staying, so the next attempt is interceptable again', async () => {
    render(<Harness enabled onConfirm={() => {}} />)
    await act(async () => {
      window.history.back()
    })
    await waitFor(() => expect(isOpen()).toBe(true))

    await userEvent.click(screen.getByTestId('stay'))
    expect(isOpen()).toBe(false)

    await act(async () => {
      window.history.back()
    })
    await waitFor(() => expect(isOpen()).toBe(true))
  })

  it('ends the interview on leave and stops intercepting afterwards', async () => {
    const onConfirm = vi.fn()
    render(<Harness enabled onConfirm={onConfirm} />)
    await act(async () => {
      window.history.back()
    })
    await waitFor(() => expect(isOpen()).toBe(true))

    await userEvent.click(screen.getByTestId('leave'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(isOpen()).toBe(false)

    // Post-confirm pops (the user navigating home during report generation)
    // must not re-open the modal.
    await act(async () => {
      window.history.back()
    })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(isOpen()).toBe(false)
  })
})
