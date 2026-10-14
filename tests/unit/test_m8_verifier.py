"""M8 applicability verification: confirmed / contradicted / unknown (PRD FR-06)."""

from __future__ import annotations

from threadline.evidence.verifier import is_simulated, verify_applicability

TARGET = {"target_system": "postgres", "target_environment": "dev"}


def _chunk(chunk_id: str, system: str | None = None, env: str | None = None, document_id: str = "doc-1") -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "source_name": "runbook.txt",
        "system_scope": system,
        "environment_scope": env,
        "content": "example passage",
    }


def _obs(evidence_id: str, *, adapter: str = "goose-mcp", system: str = "postgres", env: str = "dev", result: dict | None = None) -> dict:
    return {
        "evidence_id": evidence_id,
        "adapter": adapter,
        "tool_name": "get_service_status",
        "target_system": system,
        "target_environment": env,
        "result": result if result is not None else {},
    }


def _checks(documents=(), observations=(), **target) -> dict:
    merged = {**TARGET, **target}
    checks = verify_applicability(
        target_system=merged["target_system"],
        target_environment=merged["target_environment"],
        documents=list(documents),
        observations=list(observations),
    )
    return {check.id: check for check in checks}


def test_unscoped_document_is_unknown_not_confirmed() -> None:
    checks = _checks(documents=[_chunk("c1")])
    assert checks["document:doc-1"].status == "unknown"


def test_document_with_matching_scope_is_confirmed() -> None:
    checks = _checks(documents=[_chunk("c1", "postgres", "dev")])
    assert checks["document:doc-1"].status == "confirmed"
    assert checks["document:doc-1"].evidence_ids == ["c1"]


def test_document_scoped_to_other_environment_is_contradicted() -> None:
    checks = _checks(documents=[_chunk("c1", "postgres", "prod")])
    assert checks["document:doc-1"].status == "contradicted"


def test_one_mismatched_dimension_contradicts_even_if_other_is_missing() -> None:
    checks = _checks(documents=[_chunk("c1", "mysql", None)])
    assert checks["document:doc-1"].status == "contradicted"


def test_scope_comparison_ignores_case_and_surrounding_whitespace() -> None:
    checks = _checks(documents=[_chunk("c1", " Postgres ", "DEV")])
    assert checks["document:doc-1"].status == "confirmed"


def test_all_passages_of_one_document_share_one_check() -> None:
    checks = _checks(documents=[_chunk("c1", "postgres", "dev"), _chunk("c2", "postgres", "dev")])
    document_checks = [key for key in checks if key.startswith("document:")]
    assert document_checks == ["document:doc-1"]
    assert checks["document:doc-1"].evidence_ids == ["c1", "c2"]


def test_missing_target_makes_scope_and_document_checks_unknown() -> None:
    checks = _checks(documents=[_chunk("c1", "postgres", "dev")], target_system=None)
    assert checks["target_scope"].status == "unknown"
    assert checks["document:doc-1"].status == "unknown"


def test_no_documents_is_reported_as_unknown_documentation() -> None:
    checks = _checks(documents=[])
    assert checks["documentation_available"].status == "unknown"


def test_simulated_observation_never_confirms_applicability() -> None:
    checks = _checks(observations=[_obs("obs-1", adapter="fake")])
    assert is_simulated(_obs("obs-1", adapter="fake"))
    assert "observation:obs-1" not in checks
    assert checks["live_evidence"].status == "unknown"
    assert "simulated" in checks["live_evidence"].details.lower()


def test_real_observation_for_requested_target_is_confirmed() -> None:
    checks = _checks(observations=[_obs("obs-2", result={"service": "postgres", "environment": "dev"})])
    assert checks["observation:obs-2"].status == "confirmed"
    assert "live_evidence" not in checks


def test_real_observation_for_other_environment_is_contradicted() -> None:
    checks = _checks(observations=[_obs("obs-3", env="prod")])
    assert checks["observation:obs-3"].status == "contradicted"


def test_payload_naming_another_service_contradicts_matching_envelope() -> None:
    checks = _checks(observations=[_obs("obs-4", result={"service": "mysql", "environment": "dev"})])
    assert checks["observation:obs-4"].status == "contradicted"


def test_observation_without_declared_scope_still_confirms_from_request_envelope() -> None:
    checks = _checks(observations=[_obs("obs-5", result={"health": "green"})])
    assert checks["observation:obs-5"].status == "confirmed"


def test_observation_without_envelope_scope_is_unknown() -> None:
    checks = _checks(observations=[_obs("obs-6", system="", env="")])
    assert checks["observation:obs-6"].status == "unknown"


def test_no_check_is_ever_marked_confirmed_by_default() -> None:
    checks = _checks()
    assert all(check.status != "confirmed" for check in checks.values() if check.id != "target_scope")
    assert "unknown_requires_confirmation" not in checks
