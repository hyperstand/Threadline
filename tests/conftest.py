"""M1 test fixtures: isolated env + temp SQLite per test."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure `src/` layout is importable without an install step.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def temp_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("THREADLINE_ENV", "test")
    monkeypatch.delenv("THREADLINE_API_TOKEN", raising=False)
    return url
