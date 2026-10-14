"""M8 applicability verification (PRD FR-06).

Deterministic and model-free. Each prerequisite is classified as confirmed,
contradicted, or unknown. Unknown is never treated as confirmed, and simulated
observations (fake Goose adapter) never confirm anything.
"""

from __future__ import annotations

from typing import Any

from threadline.evidence.models import ApplicabilityCheck, CheckStatus
from threadline.integrations.goose import SIMULATED_ADAPTER_NAMES

CONFIRMED: CheckStatus = "confirmed"
CONTRADICTED: CheckStatus = "contradicted"
UNKNOWN: CheckStatus = "unknown"

_PAYLOAD_SYSTEM_KEYS = ("service", "system", "target_system")
_PAYLOAD_ENVIRONMENT_KEYS = ("environment", "target_environment")


def is_simulated(observation: dict[str, Any]) -> bool:
    return str(observation.get("adapter", "")).lower() in SIMULATED_ADAPTER_NAMES


def document_key(chunk: dict[str, Any]) -> str:
    """Stable grouping key: all passages from one document share one applicability check."""
    return str(chunk.get("document_id") or chunk.get("source_name") or chunk.get("chunk_id"))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _classify_scope(declared: dict[str, Any], target: dict[str, Any]) -> CheckStatus:
    """Any explicit mismatch contradicts. Missing metadata on either side is unknown."""
    missing = False
    for key in ("system", "environment"):
        declared_value = _text(declared.get(key))
        target_value = _text(target.get(key))
        if declared_value is None or target_value is None:
            missing = True
        elif declared_value != target_value:
            return CONTRADICTED
    return UNKNOWN if missing else CONFIRMED


def _target_text(target: dict[str, Any]) -> str:
    return f"{target.get('system') or '?'}/{target.get('environment') or '?'}"


def _scope_check(target: dict[str, Any]) -> ApplicabilityCheck:
    if _text(target.get("system")) and _text(target.get("environment")):
        return ApplicabilityCheck(
            id="target_scope",
            prerequisite="Investigation names a target system and environment",
            status=CONFIRMED,
            details=f"Target is {_target_text(target)}.",
        )
    return ApplicabilityCheck(
        id="target_scope",
        prerequisite="Investigation names a target system and environment",
        status=UNKNOWN,
        details="Target system or environment is missing; scope-based checks cannot be made.",
    )


def _document_checks(target: dict[str, Any], chunks: list[dict[str, Any]]) -> list[ApplicabilityCheck]:
    if not chunks:
        return [
            ApplicabilityCheck(
                id="documentation_available",
                prerequisite="Relevant documentation exists for the question",
                status=UNKNOWN,
                details="No documentation was retrieved for this question.",
            )
        ]

    groups: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        groups.setdefault(document_key(chunk), []).append(chunk)

    checks: list[ApplicabilityCheck] = []
    for key, group in groups.items():
        first = group[0]
        system = first.get("system_scope")
        environment = first.get("environment_scope")
        declared = {"system": system, "environment": environment}
        status = _classify_scope(declared, target)
        label = first.get("source_name") or key
        scope_text = f"{system or '?'}/{environment or '?'}"
        if status == CONFIRMED:
            details = f"Document is scoped to {scope_text}, matching the target."
        elif status == CONTRADICTED:
            details = f"Document is scoped to {scope_text}, which does not match the target {_target_text(target)}."
        else:
            details = "Document lacks complete system/environment scope metadata; applicability cannot be confirmed."
        checks.append(
            ApplicabilityCheck(
                id=f"document:{key}",
                prerequisite=f"Procedure in '{label}' applies to the target",
                status=status,
                evidence_ids=[str(chunk["chunk_id"]) for chunk in group],
                details=details,
            )
        )
    return checks


def _observation_check(observation: dict[str, Any], target: dict[str, Any]) -> ApplicabilityCheck:
    evidence_id = str(observation.get("evidence_id") or "")
    tool = observation.get("tool_name") or "tool"
    envelope = {
        "system": observation.get("target_system"),
        "environment": observation.get("target_environment"),
    }
    # The request envelope says which target the tool was called for. A payload that
    # declares a different system or environment contradicts it; a payload that
    # declares nothing neither confirms nor contradicts.
    result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
    payload_system = _text(next((result[key] for key in _PAYLOAD_SYSTEM_KEYS if key in result), None))
    payload_environment = _text(next((result[key] for key in _PAYLOAD_ENVIRONMENT_KEYS if key in result), None))
    payload_mismatch = (
        (payload_system is not None and payload_system != _text(target.get("system")))
        or (payload_environment is not None and payload_environment != _text(target.get("environment")))
    )

    envelope_status = _classify_scope(envelope, target)
    if envelope_status == CONTRADICTED or payload_mismatch:
        status, details = CONTRADICTED, f"Observation from {tool} reports a different target than {_target_text(target)}."
    elif envelope_status == CONFIRMED:
        status, details = CONFIRMED, f"Observation from {tool} was gathered for {_target_text(target)}."
    else:
        status = UNKNOWN
        details = f"Observation from {tool} does not state its target scope; it cannot confirm applicability."
    return ApplicabilityCheck(
        id=f"observation:{evidence_id}",
        prerequisite=f"Live observation from {tool} applies to the target",
        status=status,
        evidence_ids=[evidence_id],
        details=details,
    )


def _live_checks(target: dict[str, Any], observations: list[dict[str, Any]]) -> list[ApplicabilityCheck]:
    real = [item for item in observations if not is_simulated(item)]
    simulated = [item for item in observations if is_simulated(item)]
    checks = [_observation_check(item, target) for item in real]
    if not real:
        if simulated:
            details = (
                "Only simulated results from the fake Goose adapter were recorded. They are not "
                "observations of the target and cannot confirm applicability."
            )
        else:
            details = "No live operational evidence was gathered for the target."
        checks.append(
            ApplicabilityCheck(
                id="live_evidence",
                prerequisite="Live observations exist for the target",
                status=UNKNOWN,
                evidence_ids=[str(item.get("evidence_id") or "") for item in simulated],
                details=details,
            )
        )
    return checks


def verify_applicability(
    *,
    target_system: str | None,
    target_environment: str | None,
    documents: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> list[ApplicabilityCheck]:
    target = {"system": target_system, "environment": target_environment}
    checks = [_scope_check(target)]
    checks.extend(_document_checks(target, documents))
    checks.extend(_live_checks(target, observations))
    return checks
