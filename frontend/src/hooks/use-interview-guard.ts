import { useCallback, useEffect, useRef, useState } from 'react'

export interface InterviewGuard {
  /** True while the leave modal should be rendered. */
  confirmOpen: boolean
  /** Open the modal without a navigation event (e.g. an intercepted link click). */
  requestLeave: () => void
  /** Resolve the pending leave attempt with the user's choice. */
  resolveLeave: (leave: boolean) => void
}

/**
 * Guard against leaving a live interview: a refresh, tab close, or in-app
 * navigation all disconnect the LiveKit room, the worker finalizes the report
 * the moment the participant leaves, and the session's credits are spent
 * either way.
 *
 * Two mechanisms, because browsers treat those exits differently:
 *
 * - Refresh / close: ``beforeunload`` pops the browser's native confirm
 *   dialog. That dialog cannot be replaced by in-app UI, and Chrome shows a
 *   generic message, which is why the interview screen also carries an
 *   explicit "don't refresh" hint.
 * - In-app exits: a hidden sentinel entry (same URL, same state) is pushed
 *   onto the history stack while the guard is active. A Back press pops to
 *   the sentinel — the location never changes, so React Router re-renders
 *   nothing and the interview stays mounted — and the ``popstate`` handler
 *   opens the modal and immediately parks on a fresh sentinel, so repeated
 *   Back presses keep landing on same-URL entries instead of falling
 *   through to the page below the interview (a real navigation there would
 *   unmount the component rendering this modal). Staying pushes another
 *   sentinel the same way. Link clicks don't go through history, so in-page
 *   links call ``requestLeave`` after ``preventDefault``.
 *
 * Confirming the modal hands off to ``onConfirmedLeave`` (the component
 * disconnects the room and shows the report overlay); ``leaveRequested``
 * then deactivates the popstate trap so the user can navigate home freely
 * while the report generates.
 */
export function useInterviewGuard(
  enabled: boolean,
  onConfirmedLeave: () => void,
): InterviewGuard {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const leaveRequested = useRef(false)
  const onConfirmedLeaveRef = useRef(onConfirmedLeave)

  useEffect(() => {
    onConfirmedLeaveRef.current = onConfirmedLeave
  })

  const requestLeave = useCallback(() => setConfirmOpen(true), [])

  const resolveLeave = useCallback((leave: boolean) => {
    setConfirmOpen(false)
    if (leave) {
      leaveRequested.current = true
      onConfirmedLeaveRef.current()
    } else {
      // Stay: restore the interception point for the next attempt.
      history.pushState(history.state, '')
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    leaveRequested.current = false

    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      // Chrome requires returnValue to be set before it shows the dialog.
      event.returnValue = "Leaving now ends the interview and uses this session's credits."
    }

    const onPopState = () => {
      if (leaveRequested.current) return
      setConfirmOpen(true)
      // Park on a fresh sentinel immediately: a rapid second Back must land
      // on a same-URL entry, not fall through to the page below the
      // interview — that navigation unmounts the component rendering this
      // modal, ending the interview without any confirmation.
      history.pushState(history.state, '')
    }

    // The sentinel occupies the slot the user would navigate away through.
    history.pushState(history.state, '')
    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('popstate', onPopState)

    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('popstate', onPopState)
      // The sentinel is deliberately not popped: a history.back() in teardown
      // would race whatever navigation is unmounting the guard, and a
      // leftover entry is harmless (one extra Back press on an identical URL).
    }
  }, [enabled])

  // The open state is derived, not synced: when the guard deactivates (room
  // ended or torn down) any open modal disappears immediately instead of
  // lingering above the ended-report overlay. A subsequent re-enable (e.g.
  // LiveKit reconnect) restores a pending leave intent, which is consistent
  // with the guard's job of intercepting exits while the room is live.
  return { confirmOpen: confirmOpen && enabled, requestLeave, resolveLeave }
}
