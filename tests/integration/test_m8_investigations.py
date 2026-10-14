"""M8 integration: scoped upload -> investigation -> applicability -> report -> audit history.

Runs offline: the default Settings use the fake Goose adapter, so every live
result is simulated and must be labelled as such.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from threadline.config import Settings
from threadline.main import create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(THREADLINE_ENV="test", DATABASE_URL=url)
    return TestClient(create_app(settings))


def _upload(client: TestClient, name: str, text: str, system: str | None = None, env: str | None = None) -> None:
    data = {}
    if system is not None:
        data["system_scope"] = system
    if env is not None:
        data["environment_scope"] = env
    resp = client.post(
        "/api/v1/documents",
        data=data,
        files={"file": (name, text.encode(), "text/plain")},
    )
    assert resp.status_code == 201, resp.text


def _seed_documents(client: TestClient) -> None:
    _upload(client, "postgres-dev-runbook.txt", "postgres replication lag runbook for the dev cluster.", "postgres", "dev")
    _upload(client, "postgres-prod-runbook.txt", "postgres replication lag runbook for the production cluster.", "postgres", "prod")
    _upload(client, "postgres-wiki-notes.txt", "postgres replication lag notes from an unscoped wiki page.")


def _investigate(client: TestClient, **overrides) -> dict:
    payload = {
        "question": "postgres replication lag",
        "target_system": "postgres",
        "target_environment": "dev",
        **overrides,
    }
    resp = client.post("/api/v1/investigations", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_scoped_documents_are_classified_against_the_target(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        _seed_documents(client)
        body = _investigate(client)

    assert body["status"] == "completed"
    statuses = {ref["source_name"]: ref["applicability_status"] for ref in body["report"]["document_references"]}
    assert statuses == {
        "postgres-dev-runbook.txt": "confirmed",
        "postgres-prod-runbook.txt": "contradicted",
        "postgres-wiki-notes.txt": "unknown",
    }


def test_simulated_live_results_are_labelled_and_never_confirm(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        _seed_documents(client)
        body = _investigate(client)

    report = body["report"]
    assert report["observed_facts"], "fake adapter should still record a result"
    assert all(fact["simulated"] and fact["trust_status"] == "unverified" for fact in report["observed_facts"])
    checks = {check["id"]: check for check in report["applicability_checks"]}
    assert checks["live_evidence"]["status"] == "unknown"
    assert not any(key.startswith("observation:") for key in checks)
    assert "simulated" in report["executive_summary"]


def test_report_is_retrievable_and_has_no_hypotheses_without_a_model(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        _seed_documents(client)
        created = _investigate(client)
        fetched = client.get(f"/api/v1/investigations/{created['id']}/report").json()
        evidence = client.get(f"/api/v1/investigations/{created['id']}/evidence").json()

    assert fetched["report"]["hypotheses"] == []
    assert any("hypothesis" in item.lower() for item in fetched["report"]["missing_evidence"])
    assert {ref["source_name"] for ref in evidence["document_references"]} >= {"postgres-dev-runbook.txt"}
    assert evidence["applicability_checks"]


def test_audit_trail_records_workflow_tools_and_verification(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        _seed_documents(client)
        created = _investigate(client)
        events = client.get(f"/api/v1/investigations/{created['id']}/audit-events").json()["events"]

    types = [event["event_type"] for event in events]
    for expected in ("investigation.created", "workflow.node_completed", "tool.invoked", "applicability.assessed", "investigation.finalized"):
        assert expected in types, f"missing audit event {expected}"
    assert "retrieval.failed" not in types
    applicability = next(event for event in events if event["event_type"] == "applicability.assessed")
    assert applicability["safe_metadata"]["counts"]["confirmed"] >= 1
    assert all(event["correlation_id"] == created["id"] for event in events)


def test_document_only_mode_skips_live_collection_and_says_so(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        _seed_documents(client)
        body = _investigate(client, mode="document_only")

    report = body["report"]
    assert report["observed_facts"] == []
    assert any("document-only" in item.lower() for item in report["limitations"])
    assert body["status"] == "completed"


def test_retrieval_failure_is_visible_in_report_and_audit(tmp_path, monkeypatch) -> None:
    import threadline.memory.manager as manager_module

    def broken_hybrid_search(*args, **kwargs):
        raise RuntimeError("fts index missing")

    monkeypatch.setattr(manager_module, "hybrid_search", broken_hybrid_search)
    with _client(tmp_path, monkeypatch) as client:
        body = _investigate(client, mode="document_only")
        events = client.get(f"/api/v1/investigations/{body['id']}/audit-events").json()["events"]

    assert any("document retrieval failed" in item.lower() for item in body["report"]["limitations"])
    assert "retrieval.failed" in [event["event_type"] for event in events]


def test_investigation_without_documents_is_insufficient_and_explicit(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        body = _investigate(client, mode="document_only")

    assert body["status"] == "insufficient_evidence"
    assert "no conclusion can be drawn" in body["report"]["executive_summary"].lower()


def test_history_lists_investigations_newest_first(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        first = _investigate(client, mode="document_only")
        second = _investigate(client, mode="document_only", question="disk space on postgres")
        history = client.get("/api/v1/investigations?limit=10").json()

    ids = [item["id"] for item in history]
    assert ids.index(second["id"]) < ids.index(first["id"])
    assert all("report" not in item for item in history)


def test_history_limit_is_validated(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/api/v1/investigations?limit=0")
    assert resp.status_code == 422


def test_unknown_investigation_is_404_on_every_read_route(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        for suffix in ("", "/report", "/evidence", "/audit-events"):
            assert client.get(f"/api/v1/investigations/missing{suffix}").status_code == 404


def test_invalid_mode_is_rejected(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        resp = client.post(
            "/api/v1/investigations",
            json={"question": "q", "target_system": "postgres", "target_environment": "dev", "mode": "autonomous"},
        )
    assert resp.status_code == 422
