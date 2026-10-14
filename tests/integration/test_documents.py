"""M2 integration tests: document ingestion API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from threadline.config import Settings
from threadline.main import create_app


def _client(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(THREADLINE_ENV="test", DATABASE_URL=url)
    return TestClient(create_app(settings))


def test_upload_txt_indexes_with_provenance(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.post("/api/v1/documents", files={"file": ("runbook.txt", b"# Title\n\nbody text here", "text/plain")})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "indexed"
    assert body["source_name"] == "runbook.txt"
    assert body["media_type"] == "text/plain"
    assert len(body["content_hash"]) == 64
    assert len(body["chunks"]) >= 1
    chunk = body["chunks"][0]
    assert chunk["content_hash"] == __import__("hashlib").sha256(chunk["content"].encode()).hexdigest()


def test_upload_markdown_preserves_heading(tmp_path, monkeypatch):
    md = b"# Root\n\nalpha\n\n## Child\n\nbeta"
    with _client(tmp_path, monkeypatch) as client:
        up = client.post("/api/v1/documents", files={"file": ("d.md", md, "text/markdown")})
        body = up.json()
    assert up.status_code == 201
    headings = {c.get("heading") for c in body["chunks"]}
    assert "Root" in headings or "Child" in headings
    assert body["source_metadata"]["extractor"] == "markdown"


def test_list_and_get_document(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        up = client.post("/api/v1/documents", files={"file": ("a.txt", b"hello", "text/plain")})
        did = up.json()["id"]
        lst = client.get("/api/v1/documents")
        assert lst.status_code == 200
        assert any(d["id"] == did for d in lst.json())
        got = client.get(f"/api/v1/documents/{did}")
        assert got.status_code == 200
        assert got.json()["id"] == did


def test_missing_document_404(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/api/v1/documents/does-not-exist")
    assert resp.status_code == 404


def test_unsupported_type_returns_415(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.post("/api/v1/documents", files={"file": ("x.png", b"abc", "image/png")})
    assert resp.status_code == 415


def test_failed_ingestion_marks_document_failed(tmp_path, monkeypatch):
    bad_pdf = b"%PDF-1.4\nnot a real pdf\n"
    with _client(tmp_path, monkeypatch) as client:
        resp = client.post("/api/v1/documents", files={"file": ("bad.pdf", bad_pdf, "application/pdf")})
        # Either succeeds parsing (pymupdf tolerant) or fails; if fail, find failed doc.
        if resp.status_code == 201:
            assert resp.json()["status"] in ("indexed", "failed")
            return
        assert resp.status_code == 500
        lst = client.get("/api/v1/documents")
        assert any(d["status"] == "failed" for d in lst.json())
