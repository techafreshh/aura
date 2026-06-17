"""Tests for utils.config — centralized JWT secret + environment resolution.

These tests exercise the public ``get_jwt_secret`` and ``get_environment``
helpers under controlled ``os.environ`` values. We deliberately avoid
``importlib.reload`` so a failing case (which raises inside
``get_jwt_secret``) cannot leave the module in an inconsistent state for
the rest of the test suite.
"""

import pytest

from utils import config


def test_strong_secret_used(monkeypatch):
    secret = "a" * 64
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert config.get_jwt_secret() == secret
    assert config.get_environment() == "production"


def test_environment_defaults_to_development(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert config.get_environment() == "development"


def test_weak_secret_raises_in_production(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "password")
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        config.get_jwt_secret()


def test_short_secret_raises_in_production(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 16)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        config.get_jwt_secret()


def test_known_bad_default_raises_in_production(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        config.get_jwt_secret()


def test_missing_secret_raises_in_production(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        config.get_jwt_secret()


def test_missing_secret_uses_dev_fallback(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    secret = config.get_jwt_secret()
    assert isinstance(secret, str)
    assert len(secret) >= 32
    assert config.get_environment() == "development"


def test_strength_check_unit():
    assert config._is_strong_secret("a" * 32) is True
    assert config._is_strong_secret("abcd1234" * 8) is True
    assert config._is_strong_secret("short") is False
    assert config._is_strong_secret("change-me-in-production") is False
    assert config._is_strong_secret("password") is False
    assert config._is_strong_secret("") is False


def test_weak_secret_in_dev_uses_fallback(monkeypatch, capsys):
    """In dev, a weak value should be ignored in favor of the fallback."""
    monkeypatch.setenv("JWT_SECRET", "password")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    secret = config.get_jwt_secret()
    assert secret != "password"
    assert len(secret) >= 32
    captured = capsys.readouterr()
    assert "WARNING" in captured.out


def test_resolved_secret_at_import_is_valid():
    """The eager module-level JWT_SECRET must always be a strong value."""
    assert config._is_strong_secret(config.JWT_SECRET)
    assert config.ENVIRONMENT in ("development", "production", "staging", "test")
