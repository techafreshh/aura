import asyncio
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


def test_create_voice_llm_defaults_to_inference(monkeypatch):
    """An unprefixed <provider>/<model> string stays on LiveKit Inference."""
    from agent import worker

    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "devsecret")
    llm = worker.create_voice_llm("openai/gpt-4o-mini")

    assert isinstance(llm, worker.inference.LLM)
    assert llm._opts.model == "openai/gpt-4o-mini"
    assert "livekit.cloud" in llm._opts.base_url


def test_create_voice_llm_openrouter_prefix(monkeypatch):
    """An openrouter: prefix routes the voice LLM through the OpenAI plugin to OpenRouter."""
    from agent import worker

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-000")
    llm = worker.create_voice_llm("openrouter:google/gemini-2.0-flash-001")

    assert isinstance(llm, worker.livekit_openai.LLM)
    assert llm._opts.model == "google/gemini-2.0-flash-001"
    assert "openrouter.ai" in str(llm._client.base_url)


def test_create_voice_stt_defaults_to_inference(monkeypatch):
    """An unprefixed STT model string stays on LiveKit Inference."""
    from agent import worker

    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "devsecret")
    stt = worker.create_voice_stt("deepgram/nova-3")

    assert isinstance(stt, worker.inference.STT)
    assert stt._opts.model == "deepgram/nova-3"


def test_create_voice_stt_openrouter_prefix(monkeypatch):
    """An openrouter: prefix points the OpenAI-compatible STT at OpenRouter."""
    from agent import worker

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-000")
    stt = worker.create_voice_stt("openrouter:deepgram/nova-3")

    assert isinstance(stt, worker.livekit_openai.STT)
    assert stt.model == "deepgram/nova-3"
    assert "openrouter.ai" in str(stt._client.base_url)
    # Auto-detect language, matching inference.STT's no-language default.
    assert stt._opts.detect_language is True


def test_create_voice_stt_openrouter_requires_key(monkeypatch):
    """A missing OPENROUTER_API_KEY fails loudly instead of silently using OPENAI_API_KEY."""
    from agent import worker

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        worker.create_voice_stt("openrouter:deepgram/nova-3")


def test_assistant_transcript_text_extracts_string_content():
    """Assistant items yield their text via text_content (str content parts).

    Regression test: the old handler checked hasattr(part, "text") per content
    part, which never matched the plain strings livekit-agents >= 1.5 stores —
    every interviewer line was dropped and transcripts kept only the candidate.
    """
    from livekit.agents import llm
    from agent import worker

    msg = llm.ChatMessage(role="assistant", content=["Tell me about your Kafka workflow."])
    assert worker.assistant_transcript_text(msg) == "Tell me about your Kafka workflow."


def test_assistant_transcript_text_joins_multiple_parts():
    from livekit.agents import llm
    from agent import worker

    msg = llm.ChatMessage(role="assistant", content=["Part one.", "Part two."])
    assert worker.assistant_transcript_text(msg) == "Part one.\nPart two."


def test_assistant_transcript_text_ignores_user_items():
    """User turns are already captured from STT events; they must not duplicate."""
    from livekit.agents import llm
    from agent import worker

    msg = llm.ChatMessage(role="user", content=["I use Kafka daily."])
    assert worker.assistant_transcript_text(msg) == ""


def test_assistant_transcript_text_empty_content_and_whitespace():
    from livekit.agents import llm
    from agent import worker

    empty = llm.ChatMessage(role="assistant", content=[])
    assert worker.assistant_transcript_text(empty) == ""

    blank = llm.ChatMessage(role="assistant", content=["   "])
    assert worker.assistant_transcript_text(blank) == ""


def test_assistant_transcript_text_survives_duck_typed_items():
    """Plain objects without text_content degrade to empty, not a crash."""
    from agent import worker

    class _OddItem:
        role = "assistant"

    assert worker.assistant_transcript_text(_OddItem()) == ""


@pytest.mark.asyncio
async def test_end_interview_cancels_timer_saves_report_and_closes_room(monkeypatch):
    """The agent's end_interview must actually end things: stop the timer,
    persist the report, then ask the backend to delete the LiveKit room.

    Regression test: the tool previously only generated the report — the room
    stayed open, so a candidate whose interviewer finished early sat in a
    silent session with a countdown that never stopped.
    """
    from agent import worker
    from models.schemas import InterviewPlan

    plan = InterviewPlan(candidate_name="Test", extracted_skills=[], question_bank=[])
    wf = worker.InterviewWorkflow(plan=plan, session=object(), session_id="sess-end-1")
    wf.context.user_id = "user-1"
    wf.context.user_email = "user1@example.com"
    wf.timer_task = asyncio.create_task(asyncio.sleep(60))

    report_calls, close_calls = [], []

    async def _fake_report(*a, **kw):
        report_calls.append(a)

    monkeypatch.setattr(worker, "generate_and_save_report", _fake_report)

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            close_calls.append((url, kw))

            class _Resp:
                status_code = 200
                text = ""

            return _Resp()

    from types import SimpleNamespace
    monkeypatch.setattr(worker, "httpx", SimpleNamespace(AsyncClient=_FakeAsyncClient))
    monkeypatch.setenv("WORKER_API_KEY", "wk-test")

    result = await wf.end_interview()

    assert wf.timer_task.cancelling()
    assert report_calls, "report must be generated before the room is closed"
    assert len(close_calls) == 1
    url, kw = close_calls[0]
    assert url.endswith("/rooms/sess-end-1/close")
    assert kw["headers"] == {"Authorization": "Bearer wk-test"}
    assert "ended" in result.lower()
