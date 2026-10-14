"""M3 citation validation; M8 report-level validation."""

from __future__ import annotations

from collections.abc import Iterable

from threadline.evidence import CitationValidation
from threadline.evidence.models import InvestigationReport


def validate_citation_ids(ids: list[str], known_ids: set[str] | list[str]) -> CitationValidation:
    known = set(known_ids)
    valid = [cid for cid in ids if cid in known]
    invalid = [cid for cid in ids if cid not in known]
    return CitationValidation(citations=list(ids), valid=valid, invalid=invalid)


def validate_report_citations(report: InvestigationReport, known_ids: Iterable[str]) -> None:
    """Fail closed: a report that cites an ID not in the retrieved evidence is rejected."""
    validation = validate_citation_ids(report.cited_ids(), set(known_ids))
    if not validation.all_valid:
        unknown = sorted(set(validation.invalid))
        raise ValueError(f"Report cites evidence IDs that were not retrieved: {unknown}")
