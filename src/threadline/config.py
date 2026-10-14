"""Environment-based configuration and validation (M1).

SPEC §13 keys. M1 supports SQLite only; other schemes fail with an
actionable, secret-free error. Production fails closed without an API token.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from threadline.redact import redact_url

ThreadlineEnv = Literal["dev", "test", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False, populate_by_name=True)

    threadline_env: ThreadlineEnv = Field(default="dev", alias="THREADLINE_ENV")
    database_url: str = Field(default="sqlite:///./data/threadline.db", alias="DATABASE_URL")
    model_provider: str = Field(default="openai-compatible", alias="MODEL_PROVIDER")
    model_name: str = Field(default="placeholder-model", alias="MODEL_NAME")
    embedding_model: str = Field(default="placeholder-embeddings", alias="EMBEDDING_MODEL")
    goose_enabled: bool = Field(default=False, alias="GOOSE_ENABLED")
    goose_command: str = Field(default="", alias="GOOSE_COMMAND")
    goose_mcp_server: str = Field(default="", alias="GOOSE_MCP_SERVER")
    goose_tool_timeout_seconds: int = Field(default=10, alias="GOOSE_TOOL_TIMEOUT_SECONDS")
    goose_max_output_bytes: int = Field(default=65536, alias="GOOSE_MAX_OUTPUT_BYTES")
    vector_enabled: bool = Field(default=False, alias="VECTOR_ENABLED")
    vector_backend: str = Field(default="memory", alias="VECTOR_BACKEND")
    embedding_backend: str = Field(default="hash", alias="EMBEDDING_BACKEND")
    max_investigation_iterations: int = Field(default=5, alias="MAX_INVESTIGATION_ITERATIONS")
    max_tool_calls: int = Field(default=10, alias="MAX_TOOL_CALLS")
    max_investigation_seconds: int = Field(default=300, alias="MAX_INVESTIGATION_SECONDS")
    max_retrieval_results: int = Field(default=8, alias="MAX_RETRIEVAL_RESULTS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    threadline_api_token: str = Field(default="", alias="THREADLINE_API_TOKEN")

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(
                "DATABASE_URL is missing or empty. Set e.g. "
                "DATABASE_URL=sqlite:///./data/threadline.db (M1 supports SQLite only)."
            )
        scheme = value.strip().split(":", 1)[0].lower()
        if scheme != "sqlite":
            # Never echo the raw URL: it may carry credentials for future schemes.
            safe = redact_url(value)
            raise ValueError(
                f"Unsupported DATABASE_URL scheme in {safe!r}. "
                "M1 supports SQLite only (e.g. sqlite:///./data/threadline.db); "
                "PostgreSQL arrives in a later milestone."
            )
        return value.strip()

    @field_validator(
        "max_investigation_iterations",
        "max_tool_calls",
        "max_investigation_seconds",
        "max_retrieval_results",
        "goose_tool_timeout_seconds",
        "goose_max_output_bytes",
    )
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Budget/limit settings must be positive integers.")
        return value

    @model_validator(mode="after")
    def _prod_fail_closed(self) -> "Settings":
        if self.threadline_env == "prod" and not self.threadline_api_token:
            raise ValueError(
                "THREADLINE_ENV=prod requires THREADLINE_API_TOKEN to be set. "
                "Refusing to start without authentication configured (fail closed)."
            )
        return self


def get_settings() -> Settings:
    """Load settings from environment / `.env`. Raises ValidationError on misuse."""
    return Settings()
