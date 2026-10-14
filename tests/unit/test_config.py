"""M1 unit tests: config validation + secret redaction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from threadline.config import Settings
from threadline.redact import redact_secrets, redact_url


def _base_kwargs(**overrides):
    kwargs = {
        "THREADLINE_ENV": "test",
        "DATABASE_URL": "sqlite:///./data/threadline.db",
    }
    kwargs.update(overrides)
    return kwargs


def test_config_defaults_load():
    s = Settings(**_base_kwargs())
    assert s.threadline_env == "test"
    assert s.database_url.startswith("sqlite:")
    assert s.max_investigation_iterations > 0
    assert s.goose_enabled is False


def test_config_rejects_empty_database_url():
    with pytest.raises(ValidationError, match="DATABASE_URL is missing"):
        Settings(**_base_kwargs(DATABASE_URL=""))


def test_config_rejects_non_sqlite_scheme_actionably_and_without_secrets():
    raw = "postgresql://admin:s3cr3t-pw@db:5432/threadline"
    with pytest.raises(ValidationError) as exc_info:
        Settings(**_base_kwargs(DATABASE_URL=raw))
    message = str(exc_info.value)
    assert "SQLite only" in message
    # Pydantic echoes the raw input in `input_value=` by design; the app must
    # never log/return the raw error. Our boundary (redact_secrets, used by
    # main.py startup logging) must render it secret-free:
    rendered = redact_secrets(message)
    assert "s3cr3t-pw" not in rendered
    # And our own constructed portion (redacted URL) carries no userinfo:
    assert "admin" not in redact_url(raw)


def test_config_prod_without_token_fails_closed():
    with pytest.raises(ValidationError, match="THREADLINE_API_TOKEN"):
        Settings(**_base_kwargs(THREADLINE_ENV="prod", THREADLINE_API_TOKEN=""))


def test_config_prod_with_token_ok():
    s = Settings(**_base_kwargs(THREADLINE_ENV="prod", THREADLINE_API_TOKEN="dev-token"))
    assert s.threadline_env == "prod"


def test_config_rejects_nonpositive_budgets():
    with pytest.raises(ValidationError, match="positive integers"):
        Settings(**_base_kwargs(MAX_TOOL_CALLS="0"))


def test_redact_secrets_masks_tokens_and_passwords():
    assert redact_secrets("api_key=abc123") == "api_key=[REDACTED]"
    assert redact_secrets("token: hunter2") == "token=[REDACTED]"
    assert redact_secrets("Bearer abcDEF123") == "Bearer [REDACTED]"
    assert (
        redact_secrets("postgresql://admin:s3cr3t-pw@db:5432/x")
        == "postgresql://admin:[REDACTED]@db:5432/x"
    )
    # Non-secret text passes through.
    assert redact_secrets("status=ok") == "status=ok"


def test_redact_url_strips_userinfo():
    assert (
        redact_url("postgresql://admin:pw@db:5432/x")
        == "postgresql://db:5432/x"
    )
    assert redact_url("sqlite:///./data/threadline.db") == "sqlite:///./data/threadline.db"
