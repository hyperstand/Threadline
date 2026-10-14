"""M2 ingestion package."""

from __future__ import annotations

from threadline.ingestion.extractors import (
    SUPPORTED_MEDIA_TYPES,
    detect_media_type,
    extract_document,
    sha256_bytes,
)
from threadline.ingestion.extractors import MAX_CHUNK_CHARS
from threadline.ingestion.extractors import chunk_passages

__all__ = ["SUPPORTED_MEDIA_TYPES", "detect_media_type", "extract_document", "sha256_bytes", "MAX_CHUNK_CHARS", "chunk_passages"]
