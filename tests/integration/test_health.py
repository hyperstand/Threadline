"""M1 integration tests: health endpoint offline, no credentials needed."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from threadline import __version__
from threadline.config import Settings
from threadline.main import RUN_ID_HEADER, create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(THREADLINE_ENV="test", DATABASE_URL=url)
    return TestClient(create_app(settings))


def test_health_returns_version_and_env(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["env"] == "test"


def test_health_sets_run_id_header(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/health")
    run_id = resp.headers.get(RUN_ID_HEADER)
    assert run_id, "missing run-id header"
    assert re.fullmatch(r"[0-9a-f]{16}", run_id), f"bad run-id format: {run_id!r}"
    assert resp.json()["run_id"] == run_id


def test_health_body_contains_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADLINE_API_TOKEN", "super-secret-token-xyz")
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/health")
    assert "super-secret-token-xyz" not in resp.text
    assert "super-secret-token-xyz" not in str(resp.headers)


def test_unknown_route_is_404(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/nope")
    assert resp.status_code == 404
