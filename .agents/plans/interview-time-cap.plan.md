# Plan: 10-Minute Interview Time Cap with Graceful Wrap-Up

## Overview

Cap interviews at 10 minutes with a graceful 2-minute warning at the 8-minute mark. Prevents credit exhaustion from excessively long sessions (a beta tester ran for 58 minutes).

## Current State

- Worker (`backend/agent/worker.py`) has `InterviewContext.start_time` already tracking when the interview began
- Frontend (`InterviewAgent.tsx`) has an `elapsed` counter that ticks every second from connection
- `end_interview` LLM tool and `participant_disconnected` event already handle report generation on session end
- No time limit exists — the agent continues indefinitely

## Implementation

### Backend (Worker) — `backend/agent/worker.py`

**1. Add `wrap_up_triggered` field to `InterviewContext`:**
```python
@dataclass
class InterviewContext:
    plan: InterviewPlan
    current_phase: str = "Intro"
    transcript: list = field(default_factory=list)
    start_time: float = 0.0
    report_generated: bool = False
    wrap_up_triggered: bool = False  # NEW
```

**2. Add a background timer task in `entrypoint()`:**

After `session.start()`, spawn an async task that monitors elapsed time:

```python
async def time_cap_timer():
    WRAP_UP_SECONDS = 8 * 60    # 8 minutes — inject wrap-up instruction
    HARD_CAP_SECONDS = 10 * 60  # 10 minutes — force disconnect

    while not workflow.context.report_generated:
        elapsed = time.time() - workflow.context.start_time

        # Hard cap — disconnect immediately
        if elapsed >= HARD_CAP_SECONDS:
            logger.info("Hard time cap (10 min). Disconnecting.")
            try:
                session.say(
                    "I'm sorry, but we've reached the end of our allotted time. "
                    "Thank you for your participation — your report will be generated shortly."
                )
            except Exception:
                pass
            await asyncio.sleep(3)  # Let TTS finish
            await generate_and_save_report(workflow.context, session_id)
            ctx.shutdown(reason="time_cap_reached")
            return

        # Soft wrap-up at 8 minutes
        if elapsed >= WRAP_UP_SECONDS and not workflow.context.wrap_up_triggered:
            workflow.context.wrap_up_triggered = True
            logger.info("Wrap-up phase triggered (8 min).")
            try:
                session.interrupt()  # Interrupt any current agent response
                session.say(
                    "We have about two minutes remaining. "
                    "Please wrap up your current answer, and I'll ask one final question."
                )
            except Exception as e:
                logger.warning(f"Failed to inject wrap-up message: {e}")
            await asyncio.sleep(2)
            # Inject a system-level instruction for the agent
            # Use session.generate_reply or add to chat context
            # to tell the agent to ask one final question and call end_interview

        await asyncio.sleep(5)  # Check every 5 seconds

timer_task = asyncio.create_task(time_cap_timer())
```

**3. Cancel timer on disconnect:**

In `on_participant_left`, cancel the timer before generating report:
```python
@ctx.room.on("participant_disconnected")
def on_participant_left(participant):
    timer_task.cancel()
    # ... existing report generation logic
```

**4. Update system instructions** to mention time constraint:
```python
instructions = (
    # ... existing instructions ...
    "The interview has a 10-minute time limit. "
    "Aim to cover 3-4 key topics in depth rather than rushing through all questions. "
    "When you receive a wrap-up signal or notice time running short, ask one final "
    "summarizing question and then call end_interview. "
    # ... rest of instructions ...
)
```

### Frontend — `frontend/src/components/voice/InterviewAgent.tsx`

**5. Convert elapsed counter to countdown:**

Replace the existing `elapsed` state with a countdown:
```tsx
const TOTAL_SECONDS = 10 * 60;
const WARNING_SECONDS = 2 * 60;

const [remaining, setRemaining] = useState(TOTAL_SECONDS);

useEffect(() => {
  if (!hasConnected) return;
  const i = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
  return () => clearInterval(i);
}, [hasConnected]);

const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
const ss = String(remaining % 60).padStart(2, "0");
const isWarning = remaining <= WARNING_SECONDS && remaining > 0;
const isCritical = remaining <= 30 && remaining > 0;
```

**6. Add visual warning states to timer display:**
```tsx
<div className={`timer ${isWarning ? 'timer-warning' : ''} ${isCritical ? 'timer-critical' : ''}`}
     aria-label={`${mm}:${ss} remaining`}>
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10"/>
    <polyline points="12 6 12 12 16 14"/>
  </svg>
  <span>{mm}:{ss}</span>
</div>
```

**7. Add CSS for warning states** in `aura-arena.css`:
```css
.timer-warning { color: #f59e0b; }
.timer-critical { color: #ef4444; animation: pulse 1s infinite; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Wrap-up at 8 min | 2 min warning | Enough time for one final Q&A, not too early |
| Hard cutoff at 10 min | Force disconnect | Prevents credit drain; 8-min warning is enough notice |
| Timer check interval | 5 seconds | Frequent enough for accuracy, not wasteful |
| session.say() for warning | TTS message | Candidate hears the warning naturally |

## Files to Modify

- `backend/agent/worker.py` — timer task, wrap_up_triggered field, system prompt update
- `frontend/src/components/voice/InterviewAgent.tsx` — countdown timer, warning states
- `frontend/src/styles/aura-arena.css` — warning/critical timer styles

## Risks

- **Mid-sentence cutoff**: If candidate is speaking when 10 min hits, the 3-second sleep after the final TTS message may not be enough. Acceptable — the 8-min warning gives time to wrap up.
- **LiveKit API surface**: `session.interrupt()` and the exact method for injecting system-level instructions depend on the `livekit-agents>=1.5.8` API. May need to verify against SDK docs.
- **Worker API key auth**: If time cap plan is implemented before auth plan, the `session.say()` and `ctx.shutdown()` calls are internal to the worker and don't need backend auth.
