"""M3 evidence package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CitationValidation:
    citations: list[str]
    valid: list[str]
    invalid: list[str]

    @property
    def all_valid(self) -> bool:
        return len(self.invalid) == 0
