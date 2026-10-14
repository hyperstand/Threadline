"""M3 citation-backed answer construction (no live model; deterministic)."""

from __future__ import annotations

from dataclasses import dataclass

from threadline.retrieval import RetrievalResult


@dataclass
class CitedAnswer:
    question: str
    answer: str
    citations: list[str]
    results: list[RetrievalResult]


def build_cited_answer(question: str, results: list[RetrievalResult], max_results: int = 5) -> CitedAnswer:
    selected = results[:max_results]
    citations = [r.chunk_id for r in selected]
    if not selected:
        return CitedAnswer(
            question=question,
            answer="No relevant evidence found; investigation remains unresolved. Check that documents matching the question are indexed.",
            citations=[],
            results=[],
        )
    lines = [f"- {r.content.strip()[:300]}" for r in selected]
    answer = (
        f"Retrieved {len(selected)} relevant passage(s) for: {question!r}. "
        "Material findings are limited to these cited passages:\n"
        + "\n".join(lines)
    )
    return CitedAnswer(question=question, answer=answer, citations=citations, results=selected)
