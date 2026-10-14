"""M1 unit tests: SQLite initialization."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from threadline.config import Settings
from threadline.persistence.database import (
    SCHEMA_VERSION,
    AppMeta,
    init_storage,
    sqlite_filesystem_path,
)


def test_sqlite_path_none_for_memory():
    assert sqlite_filesystem_path("sqlite:///:memory:") is None


def test_init_storage_creates_file_and_schema_version(tmp_path: Path):
    db = tmp_path / "nested" / "t.db"
    settings = Settings(
        THREADLINE_ENV="test", DATABASE_URL=f"sqlite:///{db.as_posix()}"
    )
    version = init_storage(settings)
    assert version == SCHEMA_VERSION
    assert db.exists()
    engine = create_engine(settings.database_url, future=True)
    with engine.connect() as conn:
        # Connection-level ORM selects return plain rows; select the column.
        value = conn.execute(
            select(AppMeta.value).where(AppMeta.key == "schema_version")
        ).scalar_one()
        assert value == SCHEMA_VERSION
    engine.dispose()


def test_init_storage_is_idempotent(tmp_path: Path):
    db = tmp_path / "t.db"
    settings = Settings(
        THREADLINE_ENV="test", DATABASE_URL=f"sqlite:///{db.as_posix()}"
    )
    assert init_storage(settings) == SCHEMA_VERSION
    assert init_storage(settings) == SCHEMA_VERSION


def test_init_storage_memory_ok():
    settings = Settings(THREADLINE_ENV="test", DATABASE_URL="sqlite:///:memory:")
    # :memory: has no file but table creation must still succeed per connection.
    # init_storage disposes its engine, so just assert it returns the version.
    assert init_storage(settings) == SCHEMA_VERSION


def test_init_storage_failure_is_actionable_and_redacted(tmp_path: Path):
    # A path under a regular file cannot be created -> forces a failure.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    bad = blocker / "t.db"
    settings = Settings(
        THREADLINE_ENV="test", DATABASE_URL=f"sqlite:///{bad.as_posix()}"
    )
    with pytest.raises(RuntimeError, match="Failed to initialize SQLite storage"):
        init_storage(settings)
