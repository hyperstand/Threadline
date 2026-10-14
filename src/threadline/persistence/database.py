"""Persistence foundation (M1): SQLite initialization only."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from threadline.config import Settings
from threadline.redact import redact_url

SCHEMA_VERSION = "m1-1"


class Base(DeclarativeBase):
    pass


class AppMeta(Base):
    __tablename__ = "app_meta"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))


def sqlite_filesystem_path(database_url: str) -> Path | None:
    """Return the filesystem path for a SQLite URL, or None for :memory:."""
    remainder = database_url.split("sqlite:", 1)[1]
    path_text = remainder.lstrip("/")
    if database_url.startswith("sqlite:////"):
        path_text = "/" + path_text
    if path_text in ("", ":memory:", "memory"):
        return None
    path_text = path_text.split("?", 1)[0]
    return Path(path_text)


def init_storage(settings: Settings) -> str:
    try:
        from threadline.persistence import models as _models  # noqa: F401
    except Exception:
        pass
    """Create parent dirs, connect to SQLite, and ensure base tables exist.

    Returns the schema version string. Raises RuntimeError with an actionable,
    secret-free message on failure.
    """
    safe_url = redact_url(settings.database_url)
    try:
        fs_path = sqlite_filesystem_path(settings.database_url)
        if fs_path is not None and str(fs_path):
            parent = fs_path.parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(settings.database_url, future=True)
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            # NOTE: executed via a Connection (not a Session), so select the
            # plain key column rather than the ORM entity.
            existing = conn.execute(
                select(AppMeta.key).where(AppMeta.key == "schema_version")
            ).scalar_one_or_none()
            if existing is None:
                conn.execute(
                    AppMeta.__table__.insert().values(
                        key="schema_version", value=SCHEMA_VERSION
                    )
                )
            else:
                conn.execute(
                    AppMeta.__table__.update()
                    .where(AppMeta.key == "schema_version")
                    .values(value=SCHEMA_VERSION)
                )
        engine.dispose()
        return SCHEMA_VERSION
    except Exception as exc:
        raise RuntimeError(
            f"Failed to initialize SQLite storage for {safe_url}: {type(exc).__name__}. "
            "Check that DATABASE_URL is a writable sqlite path, e.g. "
            "sqlite:///./data/threadline.db"
        ) from exc


def create_engine_from_settings(settings: Settings):
    return create_engine(settings.database_url, future=True)


def create_session_factory(settings: Settings):
    from sqlalchemy.engine import Engine

    engine = create_engine_from_settings(settings)
    return engine, sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
