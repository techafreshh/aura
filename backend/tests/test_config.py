"""Tests for utils.config — centralized JWT secret + environment resolution.

These tests exercise the public ``get_jwt_secret`` and ``get_environment``
helpers under controlled ``os.environ`` values. We deliberately avoid
``importlib.reload`` so a failing case (which raises inside
``get_jwt_secret``) cannot leave the module in an inconsistent state for
the rest of the test suite.
"""

import pytest

from utils import config

# The AI model resolution helpers. All of them must be tested through the
# getters, never by re-importing the module, for the same reason as above.
MODEL_ENV_VARS = ("REASONING_MODEL", "PARSER_MODEL", "EVALUATOR_MODEL", "REPORTER_MODEL", "LIVEKIT_LLM_MODEL")


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


# --- AI model resolution ----------------------------------------------------


@pytest.fixture
def clear_model_env(monkeypatch):
    """Remove any ambient model env vars so each test starts from defaults."""
    for var in MODEL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_reasoning_model_defaults_when_env_unset(clear_model_env):
    for agent in ("parser", "evaluator", "reporter"):
        assert config.get_reasoning_model(agent) == "openrouter:google/gemini-2.0-flash-001"


def test_shared_reasoning_model_applies_to_all_agents(clear_model_env, monkeypatch):
    monkeypatch.setenv("REASONING_MODEL", "openrouter:anthropic/claude-3.5-haiku")
    for agent in ("parser", "evaluator", "reporter"):
        assert config.get_reasoning_model(agent) == "openrouter:anthropic/claude-3.5-haiku"


def test_per_agent_model_overrides_shared(clear_model_env, monkeypatch):
    monkeypatch.setenv("REASONING_MODEL", "openrouter:shared/model")
    monkeypatch.setenv("PARSER_MODEL", "openrouter:parser/model")
    assert config.get_reasoning_model("parser") == "openrouter:parser/model"
    assert config.get_reasoning_model("evaluator") == "openrouter:shared/model"
    assert config.get_reasoning_model("reporter") == "openrouter:shared/model"


def test_per_agent_model_without_shared(clear_model_env, monkeypatch):
    monkeypatch.setenv("REPORTER_MODEL", "openrouter:only/reporter")
    assert config.get_reasoning_model("reporter") == "openrouter:only/reporter"
    assert config.get_reasoning_model("parser") == "openrouter:google/gemini-2.0-flash-001"


def test_blank_model_values_are_treated_as_unset(clear_model_env, monkeypatch):
    monkeypatch.setenv("REASONING_MODEL", "   ")
    monkeypatch.setenv("EVALUATOR_MODEL", "")
    assert config.get_reasoning_model("evaluator") == "openrouter:google/gemini-2.0-flash-001"


def test_model_value_whitespace_is_stripped(clear_model_env, monkeypatch):
    monkeypatch.setenv("PARSER_MODEL", "  openrouter:parser/model  ")
    assert config.get_reasoning_model("parser") == "openrouter:parser/model"


def test_resolved_models_at_import_match_getters():
    """The eager module-level constants must agree with the getter logic.

    No fixture here: both sides must read the *same* environment — the
    constants were resolved at import, the getter at call time.
    """
    assert config.PARSER_MODEL == config.get_reasoning_model("parser")
    assert config.EVALUATOR_MODEL == config.get_reasoning_model("evaluator")
    assert config.REPORTER_MODEL == config.get_reasoning_model("reporter")


def test_voice_llm_model_default(clear_model_env):
    assert config.get_voice_llm_model() == "openai/gpt-4o-mini"


def test_voice_llm_model_override(clear_model_env, monkeypatch):
    monkeypatch.setenv("LIVEKIT_LLM_MODEL", "openai/gpt-4.1-mini")
    assert config.get_voice_llm_model() == "openai/gpt-4.1-mini"


def test_voice_llm_model_blank_treated_as_unset(clear_model_env, monkeypatch):
    monkeypatch.setenv("LIVEKIT_LLM_MODEL", "  ")
    assert config.get_voice_llm_model() == "openai/gpt-4o-mini"


def test_resolved_voice_llm_model_at_import_matches_getter():
    assert config.LIVEKIT_LLM_MODEL == config.get_voice_llm_model()


def test_default_invite_expiry_hours_env_override(monkeypatch):
    """DEFAULT_INVITE_EXPIRY_HOURS reads its env var, falling back to 24."""
    monkeypatch.setenv("DEFAULT_INVITE_EXPIRY_HOURS", "48")
    assert config.get_default_invite_expiry_hours() == 48


def test_default_invite_expiry_hours_malformed_falls_back(monkeypatch):
    """A malformed or non-positive value falls back to 24, like the quota var."""
    for bad in ("not-a-number", "0", "-3"):
        monkeypatch.setenv("DEFAULT_INVITE_EXPIRY_HOURS", bad)
        assert config.get_default_invite_expiry_hours() == 24


def test_default_invite_expiry_hours_default_when_unset(monkeypatch):
    monkeypatch.delenv("DEFAULT_INVITE_EXPIRY_HOURS", raising=False)
    assert config.get_default_invite_expiry_hours() == 24
