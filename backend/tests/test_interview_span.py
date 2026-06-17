import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_interview_completed_span_is_emitted(monkeypatch):
    """generate_and_save_report emits an interview_completed span with duration/score attrs."""
    from agent import worker
    from models.context import InterviewContext
    from models.schemas import InterviewPlan, FinalReport, SectionGrade

    captured = {}

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
        def start_as_current_span(self, name):
            captured["name"] = name
            captured["span"] = _FakeSpan(name)
            return captured["span"]

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
    monkeypatch.setattr(worker.otel_trace, "get_tracer", lambda name: _FakeTracer())

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

    assert captured["name"] == "interview_completed"
    span = captured["span"]
    assert span.attrs["langfuse.session.id"] == "span-test-session"
    assert span.attrs["langfuse.user.id"] == "user-99"
    assert span.attrs["aura.overall_score"] == 85
    assert span.attrs["aura.recommendation"] == "Strong Hire"
    assert span.attrs["aura.section_count"] == 1
    assert span.attrs["aura.transcript_entries"] == 0
    assert span.attrs["aura.duration_seconds"] >= 0