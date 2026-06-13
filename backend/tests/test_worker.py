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
