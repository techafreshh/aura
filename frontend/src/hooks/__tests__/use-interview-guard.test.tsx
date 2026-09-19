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
  const { confirmOpen, requestLeave, resolveLeave } = useInterviewGuard(enabled, onConfirm)
  return (
    <div data-testid="modal" data-open={confirmOpen ? 'true' : 'false'}>
      <button data-testid="request" onClick={() => requestLeave()}>request</button>
      <button data-testid="stay" onClick={() => resolveLeave(false)}>stay</button>
      <button data-testid="leave" onClick={() => resolveLeave(true)}>leave</button>
    </div>
  )
}

const isOpen = () => screen.getByTestId('modal').dataset.open === 'true'

/**
 * This suite drives history and clicks explicitly inside act: jsdom
 * dispatches `popstate` on a macrotask that can land after the act scope
 * closes, and user-event's click dispatches are not act-wrapped in this
 * setup — so the guard's state updates would land outside act and race the
 * assertions (tripping React's act warning along the way). Awaiting the
 * popstate event / the click inside an act scope pins every state update
 * inside act, deterministically. Every backInAct call site has a history
 * entry below the current one (the guard's sentinel or a pushed runway), so
 * the popstate event always fires.
 */
const backInAct = async () => {
  await act(async () => {
    const popped = new Promise<void>((resolve) =>
      window.addEventListener('popstate', () => resolve(), { once: true }),
    )
    window.history.back()
    await popped
  })
}

const clickInAct = async (element: HTMLElement) => {
  await act(async () => {
    await userEvent.click(element)
  })
}

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
    await backInAct()
    await waitFor(() => expect(isOpen()).toBe(true))
    // The sentinel shares the interview URL, so popping it changes nothing
    // visible — React Router (and the interview) stay mounted.
    expect(window.location.pathname).toBe('/')
  })

  it('re-arms after staying, so the next attempt is interceptable again', async () => {
    render(<Harness enabled onConfirm={() => {}} />)
    await backInAct()
    await waitFor(() => expect(isOpen()).toBe(true))

    await clickInAct(screen.getByTestId('stay'))
    expect(isOpen()).toBe(false)

    await backInAct()
    await waitFor(() => expect(isOpen()).toBe(true))
  })

  it('opens the modal via requestLeave without any navigation event', async () => {
    // The brand-link path: preventDefault'ed clicks never touch history, so
    // requestLeave must open the modal on its own — and Stay must still arm
    // interception for a later Back press.
    render(<Harness enabled onConfirm={() => {}} />)
    await clickInAct(screen.getByTestId('request'))
    expect(isOpen()).toBe(true)
    expect(window.location.pathname).toBe('/')

    await clickInAct(screen.getByTestId('stay'))
    expect(isOpen()).toBe(false)

    await backInAct()
    await waitFor(() => expect(isOpen()).toBe(true))
  })

  it('ends the interview on leave and stops intercepting afterwards', async () => {
    const onConfirm = vi.fn()
    render(<Harness enabled onConfirm={onConfirm} />)
    await backInAct()
    await waitFor(() => expect(isOpen()).toBe(true))

    await clickInAct(screen.getByTestId('leave'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(isOpen()).toBe(false)

    // Post-confirm pops (the user navigating home during report generation)
    // must not re-open the modal. pushState first so the back actually has
    // an entry to pop — otherwise back() is a no-op here and the trap's
    // post-confirm behavior would go unexercised.
    window.history.pushState({}, '')
    await backInAct()
    expect(isOpen()).toBe(false)
  })

  it('keeps intercepting rapid double backs instead of escaping the URL', async () => {
    // Simulate the real flow: the user was on the landing page, navigated to
    // the interview, and the guard pushed its sentinel. After the first Back
    // opens the modal, a rapid second Back must land on a same-URL entry
    // again — not fall through to the page below, which would unmount the
    // interview (and this modal) without any confirmation.
    window.history.pushState({}, '', '/landing')
    window.history.pushState({}, '', '/interview')
    render(<Harness enabled onConfirm={() => {}} />)
    await backInAct()
    await waitFor(() => expect(isOpen()).toBe(true))

    await backInAct()
    await waitFor(() => expect(isOpen()).toBe(true))
    expect(window.location.pathname).toBe('/interview')
  })
})
