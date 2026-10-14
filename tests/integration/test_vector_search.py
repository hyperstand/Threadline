"""M4 integration tests: semantic/vector retrieval and hybrid ranking."""

from __future__ import annotations

from fastapi.testclient import TestClient

from threadline.config import Settings
from threadline.main import create_app


def _client(tmp_path, monkeypatch, vector_enabled=False):
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    # Do not accidentally inherit production settings from the environment.
    monkeypatch.delenv("VECTOR_ENABLED", raising=False)
    settings = Settings(
        THREADLINE_ENV="test",
        DATABASE_URL=url,
        VECTOR_ENABLED=vector_enabled,
        VECTOR_BACKEND="memory",
        EMBEDDING_BACKEND="hash",
    )
    return TestClient(create_app(settings))


def test_vector_mode_returns_semantic_result(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, vector_enabled=True) as client:
        r = client.post("/api/v1/documents", files={"file": ("a.txt", b"password reset guide", "text/plain")})
        assert r.status_code == 201
        resp = client.get("/api/v1/search", params={"q": "password reset", "mode": "vector"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        result = body["results"][0]
        assert result["source_name"] == "a.txt"
        assert result["search_type"] == "vector"
        assert result["semantic_score"] is not None
        assert result["score"] is not None


def test_hybrid_mode_combines_and_deduplicates(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, vector_enabled=True) as client:
        client.post("/api/v1/documents", files={"file": ("a.txt", b"password reset guide", "text/plain")})
        resp = client.get("/api/v1/search", params={"q": "password reset", "mode": "hybrid"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        result = body["results"][0]
        assert result["search_type"] == "hybrid"
        assert result["semantic_score"] is not None
        assert result["keyword_score"] is not None
        assert result["fusion_score"] is not None


def test_vector_mode_fallback_when_unavailable(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, vector_enabled=False) as client:
        client.post("/api/v1/documents", files={"file": ("a.txt", b"password reset guide", "text/plain")})
        resp = client.get("/api/v1/search", params={"q": "password reset", "mode": "vector"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


def test_hybrid_falls_back_to_keyword_when_vector_unavailable(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, vector_enabled=False) as client:
        client.post("/api/v1/documents", files={"file": ("a.txt", b"password reset guide", "text/plain")})
        resp = client.get("/api/v1/search", params={"q": "password reset", "mode": "hybrid"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["results"][0]["search_type"] == "keyword"


def test_answer_citations_valid_for_vector_mode(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, vector_enabled=True) as client:
        client.post("/api/v1/documents", files={"file": ("a.txt", b"password reset guide", "text/plain")})
        resp = client.post("/api/v1/answers", json={"question": "password reset", "limit": 3})
        assert resp.status_code == 200
        body = resp.json()
        assert body["citation_check"]["all_valid"] is True
        assert len(body["citations"]) == len(body["results"])
        assert body["results"][0]["semantic_score"] is not None