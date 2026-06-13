import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

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

def test_interview_context_has_wrap_up_field():
    """Verify that InterviewContext has the wrap_up_triggered field."""
    from agent.worker import InterviewContext
    from models.schemas import InterviewPlan

    plan = InterviewPlan(candidate_name="Test", extracted_skills=[], question_bank=[])
    ctx = InterviewContext(plan=plan)
    assert hasattr(ctx, 'wrap_up_triggered')
    assert ctx.wrap_up_triggered is False

def test_interview_context_wrap_up_default():
    """Verify wrap_up_triggered defaults to False."""
    from agent.worker import InterviewContext
    from models.schemas import InterviewPlan

    plan = InterviewPlan(candidate_name="Test", extracted_skills=[], question_bank=[])
    ctx = InterviewContext(plan=plan)
    assert ctx.wrap_up_triggered is False
    ctx.wrap_up_triggered = True
    assert ctx.wrap_up_triggered is True
