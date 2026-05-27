import os
from unittest.mock import patch, MagicMock
import utils.tracing


def _reset():
    utils.tracing._provider = None


def test_setup_langfuse_returns_none_when_unconfigured():
    """Tracing gracefully disabled when env vars are missing."""
    _reset()
    # Remove langfuse vars if they happen to be set
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        os.environ.pop(key, None)
    result = utils.tracing.setup_langfuse()
    assert result is None


@patch("pydantic_ai.Agent.instrument_all")
@patch("langfuse.Langfuse")
def test_setup_langfuse_initializes_when_configured(mock_langfuse_cls, mock_instrument):
    """Tracing initializes when all env vars are present."""
    _reset()
    os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-test"
    os.environ["LANGFUSE_SECRET_KEY"] = "sk-test"
    os.environ["LANGFUSE_BASE_URL"] = "http://localhost:3001"
    try:
        result = utils.tracing.setup_langfuse()
        assert result is not None
        mock_langfuse_cls.assert_called_once()
        mock_instrument.assert_called_once()
    finally:
        os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
        os.environ.pop("LANGFUSE_SECRET_KEY", None)
        os.environ.pop("LANGFUSE_BASE_URL", None)


def test_setup_langfuse_does_not_raise_on_error():
    """Tracing never crashes the app."""
    _reset()
    os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-test"
    os.environ["LANGFUSE_SECRET_KEY"] = "sk-test"
    os.environ["LANGFUSE_BASE_URL"] = "http://localhost:3001"
    try:
        with patch("langfuse.Langfuse", side_effect=Exception("connection refused")):
            result = utils.tracing.setup_langfuse()
        assert result is None
    finally:
        os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
        os.environ.pop("LANGFUSE_SECRET_KEY", None)
        os.environ.pop("LANGFUSE_BASE_URL", None)
