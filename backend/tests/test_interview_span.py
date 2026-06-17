import time
import pytest


class _FakeSpan:
    def __init__(self, name):
        self.name = name
        self.attrs = {}

    def set_attribute(self, key, value):
        self.attrs[key] = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeTracer:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, name):
        span = _FakeSpan(name)
        self.spans.append(span)
        return span


@pytest.mark.asyncio
async def test_interview_completed_span_is_emitted(monkeypatch):
    """generate_and_save_report emits an interview_completed span with duration/score attrs."""
    from agent import worker
    from models.context import InterviewContext
    from models.schemas import InterviewPlan, FinalReport, SectionGrade

    fake_tracer = _FakeTracer()
    plan = InterviewPlan(candidate_name="Test", extracted_skills=[], question_bank=[])
    ctx = InterviewContext(plan=plan)
    ctx.user_id = "user-99"
    ctx.start_time = time.time() - 12.0

    fake_report = FinalReport(
        candidate_name="Test",
        overall_score=85,
        section_grades=[SectionGrade(section_name="Tech", score=9, comments="ok")],
        strengths=["Python"],
        weaknesses=["Speed"],
        recommendation="Strong Hire",
        summary="Solid candidate.",
    )

    class _Result:
        output = fake_report

    async def _fake_run(prompt):
        return _Result()

    monkeypatch.setattr(worker.reporter_agent, "run", _fake_run)
    monkeypatch.setattr(worker.otel_trace, "get_tracer", lambda name: fake_tracer)

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, *a, **kw):
            class _R:
                status_code = 200
                text = ""
            return _R()

    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeAsyncClient)

    await worker.generate_and_save_report(ctx, "span-test-session")

    assert len(fake_tracer.spans) == 1
    span = fake_tracer.spans[0]
    assert span.name == "interview_completed"
    assert span.attrs["langfuse.session.id"] == "span-test-session"
    assert span.attrs["langfuse.user.id"] == "user-99"
    assert span.attrs["aura.overall_score"] == 85
    assert span.attrs["aura.recommendation"] == "Strong Hire"
    assert span.attrs["aura.section_count"] == 1
    assert span.attrs["aura.transcript_entries"] == 0
    assert span.attrs["aura.duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_interview_session_root_span_is_emitted(monkeypatch):
    """entrypoint emits the root interview_session span with user identity and plan attrs."""
    from agent import worker

    fake_tracer = _FakeTracer()

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "plan": {
                    "candidate_name": "Alice",
                    "extracted_skills": ["Python", "FastAPI"],
                    "question_bank": ["Q1", "Q2", "Q3"],
                },
                "user_id": "user-42",
                "user_email": "alice@example.com",
            }

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return _FakeResponse()

        async def post(self, *a, **kw):
            class _R:
                status_code = 200
                text = ""
            return _R()

    class _FakeCtx:
        def __init__(self):
            class _Room:
                name = "test-session-root"
                def on(self, event):
                    def decorator(fn):
                        return fn
                    return decorator
            self.room = _Room()

        async def connect(self, *a, **kw):
            return None

        def add_shutdown_callback(self, fn):
            return None

        def shutdown(self, *a, **kw):
            return None

    class _FakeAgentSession:
        def __init__(self, *a, **kw):
            self.say_calls = []

        def on(self, event):
            def decorator(fn):
                return fn
            return decorator

        async def start(self, agent, room=None):
            return None

        def say(self, *a, **kw):
            self.say_calls.append((a, kw))

    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(worker.otel_trace, "get_tracer", lambda name: fake_tracer)
    monkeypatch.setattr(worker, "_run_interview", lambda *a, **kw: _async_noop())
    monkeypatch.setattr(worker.voice, "AgentSession", _FakeAgentSession)
    monkeypatch.setattr(worker.silero.VAD, "load", staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(worker.inference, "STT", lambda *a, **kw: None)
    monkeypatch.setattr(worker.inference, "LLM", lambda *a, **kw: None)
    monkeypatch.setattr(worker.inference, "TTS", lambda *a, **kw: None)

    await worker.entrypoint(_FakeCtx())

    assert len(fake_tracer.spans) == 1
    span = fake_tracer.spans[0]
    assert span.name == "interview_session"
    assert span.attrs["langfuse.session.id"] == "test-session-root"
    assert span.attrs["langfuse.user.id"] == "user-42"
    assert span.attrs["langfuse.user.email"] == "alice@example.com"
    assert span.attrs["aura.candidate_name"] == "Alice"
    assert span.attrs["aura.skills"] == "Python,FastAPI"
    assert span.attrs["aura.question_count"] == 3


async def _async_noop():
    return None
