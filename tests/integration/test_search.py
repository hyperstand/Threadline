"""M3 integration tests: keyword retrieval and citation-backed answers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from threadline.config import Settings
from threadline.main import create_app


def _client(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(THREADLINE_ENV="test", DATABASE_URL=url)
    return TestClient(create_app(settings))


def test_keyword_search_returns_provenance(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/v1/documents", files={"file": ("a.txt", b"alpha service error logs", "text/plain")})
        client.post("/api/v1/documents", files={"file": ("b.txt", b"gamma unrelated content", "text/plain")})
        resp = client.get("/api/v1/search", params={"q": "service error"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    result = body["results"][0]
    assert result["source_name"] == "a.txt"
    assert result["content_hash"]
    assert "service" in result["content"]
    assert len(result["chunk_id"]) > 0
    assert result["search_type"].startswith("keyword")


def test_search_filters_by_document_type(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/v1/documents", files={"file": ("a.txt", b"service failure details", "text/plain")})
        client.post("/api/v1/documents", files={"file": ("b.md", b"service failure details", "text/markdown")})
        resp = client.get("/api/v1/search", params={"q": "service failure", "document_type": "txt"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert all(r["media_type"] == "text/plain" for r in resp.json()["results"])


def test_answer_citations_all_resolve(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        up = client.post("/api/v1/documents", files={"file": ("a.txt", b"important observation evidence", "text/plain")})
        doc_id = up.json()["id"]
        resp = client.post("/api/v1/answers", json={"question": "important observation", "limit": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["citation_check"]["all_valid"] is True
    assert len(body["citations"]) == len(body["results"])
    for cid in body["citations"]:
        assert any(r["chunk_id"] == cid for r in body["results"])
    # retrieved IDs should be associated with known document
    assert all(r["document_id"] == doc_id for r in body["results"])


def test_empty_search_returns_no_results(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/v1/documents", files={"file": ("a.txt", b"hello", "text/plain")})
        resp = client.get("/api/v1/search", params={"q": "zzzznonexistent"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["results"] == []
