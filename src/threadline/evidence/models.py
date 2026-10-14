"""M8 evidence and report schema (PRD FR-06, FR-07; SPEC §4, §8).

Every ID a report cites must resolve to a retrieved document chunk or a
recorded observation. Validation lives in `threadline.evidence.citations`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["confirmed", "contradicted", "unknown"]
TrustStatus = Literal["observed", "source_backed", "inferred", "unverified", "verified"]
HypothesisStatus = Literal["open", "supported", "contradicted", "verified", "rejected"]

REPORT_DISCLAIMER = (
    "Generated recommendations are not proof of a diagnosis. Verify observations "
    "in the target environment before acting."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApplicabilityCheck(BaseModel):
    """One prerequisite classified against known target facts. Unknown is never confirmed."""

    id: str
    prerequisite: str
    status: CheckStatus
    evidence_ids: list[str] = Field(default_factory=list)
    details: str


class ObservedFact(BaseModel):
    """A live observation. Simulated results carry trust_status "unverified"."""

    evidence_id: str
    source: str
    excerpt: str
    trust_status: TrustStatus
    simulated: bool = False
    observed_at: str | None = None


class DocumentReference(BaseModel):
    """A retrieved document passage with its scope check result."""

    chunk_id: str
    document_id: str | None = None
    source_name: str | None = None
    version: str | None = None
    page_number: int | None = None
    section_path: str | None = None
    heading: str | None = None
    excerpt: str = ""
    applicability_status: CheckStatus = "unknown"


class Hypothesis(BaseModel):
    statement: str
    status: HypothesisStatus = "open"
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)


class ReportScope(BaseModel):
    system: str | None = None
    environment: str | None = None


class InvestigationReport(BaseModel):
    """Structured investigation report (PRD FR-07)."""

    run_id: str
    generated_at: datetime = Field(default_factory=_now)
    request: str
    target_scope: ReportScope
    executive_summary: str
    observed_facts: list[ObservedFact] = Field(default_factory=list)
    document_references: list[DocumentReference] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    applicability_checks: list[ApplicabilityCheck] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    risks_and_required_approvals: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    investigation_plan: list[str] = Field(default_factory=list)
    disclaimer: str = REPORT_DISCLAIMER

    def cited_ids(self) -> list[str]:
        ids = [ref.chunk_id for ref in self.document_references]
        ids += [fact.evidence_id for fact in self.observed_facts]
        for check in self.applicability_checks:
            ids.extend(check.evidence_ids)
        for hypothesis in self.hypotheses:
            ids.extend(hypothesis.supporting_evidence_ids)
            ids.extend(hypothesis.contradicting_evidence_ids)
        return ids
