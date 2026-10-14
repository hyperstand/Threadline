"""M3 citation validation."""

from __future__ import annotations

from threadline.evidence import CitationValidation


def validate_citation_ids(ids: list[str], known_ids: set[str] | list[str]) -> CitationValidation:
    known = set(known_ids)
    valid = [cid for cid in ids if cid in known]
    invalid = [cid for cid in ids if cid not in known]
    return CitationValidation(citations=list(ids), valid=valid, invalid=invalid)
