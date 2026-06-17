import sentry_sdk


def test_sentry_sdk_installed():
    """sentry-sdk package is importable."""
    assert hasattr(sentry_sdk, "init")
    assert hasattr(sentry_sdk, "capture_exception")


def test_backend_imports_sentry():
    """Backend main module imports and uses sentry_sdk."""
    import api.main
    import inspect
    source = inspect.getsource(api.main)
    assert "sentry_sdk.init(" in source


def test_worker_imports_sentry():
    """Worker module imports and uses sentry_sdk."""
    import agent.worker
    import inspect
    source = inspect.getsource(agent.worker)
    assert "sentry_sdk.init(" in source


def test_sentry_init_uses_env_var():
    """Sentry init reads DSN from SENTRY_DSN env var."""
    import api.main
    import inspect
    source = inspect.getsource(api.main)
    assert 'os.getenv("SENTRY_DSN")' in source


def test_sentry_init_has_traces_sample_rate():
    """Sentry init configures traces_sample_rate."""
    import api.main
    import inspect
    source = inspect.getsource(api.main)
    assert "traces_sample_rate=1.0" in source


def test_sentry_init_has_environment():
    """Sentry init configures environment from the shared config module."""
    import api.main
    import inspect
    source = inspect.getsource(api.main)
    # ENVIRONMENT is now sourced from utils.config (single source of truth) so
    # Sentry, CORS, and the JWT-secret guard all agree on a default.
    assert "environment=ENVIRONMENT" in source or 'os.getenv("ENVIRONMENT"' in source
