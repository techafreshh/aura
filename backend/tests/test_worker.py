import time
import pytest


def test_worker_import():
    """Verify that the worker script can be imported without errors."""
    try:
        from agent import worker
        assert worker is not None
    except ImportError as e:
        pytest.fail(f"Failed to import worker: {str(e)}")
    except Exception as e:
        pytest.fail(f"Unexpected error importing worker: {str(e)}")


def test_worker_entrypoint_exists():
    """Verify that the entrypoint function exists in the worker script."""
    from agent import worker
    assert hasattr(worker, 'entrypoint')
    assert callable(worker.entrypoint)


def test_interview_context_wrap_up_field():
    """Verify InterviewContext has wrap_up_triggered field with correct default."""
    from models.context import InterviewContext
    from models.schemas import InterviewPlan

    plan = InterviewPlan(candidate_name="Test", extracted_skills=[], question_bank=[])
    ctx = InterviewContext(plan=plan)
    assert ctx.wrap_up_triggered is False
    ctx.wrap_up_triggered = True
    assert ctx.wrap_up_triggered is True


def test_interview_context_user_fields():
    """Verify InterviewContext has user_id and user_email fields with correct defaults."""
    from models.context import InterviewContext
    from models.schemas import InterviewPlan

    plan = InterviewPlan(candidate_name="Test", extracted_skills=[], question_bank=[])
    ctx = InterviewContext(plan=plan)
    assert ctx.user_id == "anonymous"
    assert ctx.user_email == ""

    ctx.user_id = "user-123"
    ctx.user_email = "user@example.com"
    assert ctx.user_id == "user-123"
    assert ctx.user_email == "user@example.com"


@pytest.mark.asyncio
async def test_generate_and_save_report_accepts_user_args(monkeypatch):
    """generate_and_save_report should accept user_id and user_email args and persist them to context."""
    from agent import worker
    from models.context import InterviewContext
    from models.schemas import InterviewPlan

    plan = InterviewPlan(candidate_name="Test", extracted_skills=[], question_bank=[])
    ctx = InterviewContext(plan=plan)
    ctx.start_time = time.time() - 5.0

    # Patch reporter_agent and httpx to avoid real network/LLM calls
    from models.schemas import FinalReport, SectionGrade

    fake_report = FinalReport(
        candidate_name="Test",
        overall_score=80,
        section_grades=[SectionGrade(section_name="Technical", score=8, comments="Good")],
        strengths=["Python"],
        weaknesses=["Concurrency"],
        recommendation="Hire",
        summary="Good candidate.",
    )

    class _FakeRun:
        def __init__(self):
            self._awaitable = None

        async def _run_async(self):
            class _Result:
                def __init__(self, output):
                    self.output = output
            return _Result(fake_report)

    async def _fake_run(prompt):
        class _Result:
            output = fake_report
        return _Result()

    monkeypatch.setattr(worker.reporter_agent, "run", _fake_run)

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            class _Resp:
                status_code = 200
                text = ""
            return _Resp()

    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeAsyncClient)

    await worker.generate_and_save_report(ctx, "test-session-id", user_id="user-42", user_email="user42@example.com")

    assert ctx.user_id == "user-42"
    assert ctx.user_email == "user42@example.com"
    assert ctx.report_generated is True
