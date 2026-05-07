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
