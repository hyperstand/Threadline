"""M2 ingestion: extractors and chunking with source passage provenance."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from docx import Document as DocxDocument
# Available in installed PyMuPDF package.
import pymupdf as fitz

SUPPORTED_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}

MAX_CHUNK_CHARS = 1200


@dataclass
class ExtractedPassage:
    text: str
    page_number: int | None = None
    section_path: str | None = None
    heading: str | None = None


@dataclass
class ExtractedDocument:
    passages: list[ExtractedPassage]
    page_count: int | None
    extractor: str


@dataclass
class Chunk:
    content: str
    chunk_index: int
    page_number: int | None = None
    section_path: str | None = None
    heading: str | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_media_type(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    return SUPPORTED_MEDIA_TYPES.get(ext)


def extract_document(filename: str, data: bytes) -> ExtractedDocument:
    media_type = detect_media_type(filename)
    if media_type == "application/pdf":
        return _extract_pdf(data)
    if media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(data)
    if media_type in ("text/markdown", "text/plain"):
        return _extract_text(data, markdown=(media_type == "text/markdown"))
    raise ValueError(f"Unsupported document type for {filename!r}.")


def _extract_pdf(data: bytes) -> ExtractedDocument:
    doc = fitz.open(stream=data, filetype="pdf")
    passages: list[ExtractedPassage] = []
    for i, page in enumerate(doc, start=1):
        try:
            page_text = page.get_text() or ""
        except Exception:
            page_text = ""
        passages.append(ExtractedPassage(text=page_text, page_number=i))
    page_count = doc.page_count
    doc.close()
    return ExtractedDocument(passages=passages, page_count=page_count, extractor="pymupdf")


def _extract_docx(data: bytes) -> ExtractedDocument:
    doc = DocxDocument(io.BytesIO(data))
    current_headings: list[str] = []
    passages: list[ExtractedPassage] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        style = (para.style.name if para.style is not None else "").lower()
        if style.startswith("heading"):
            if text:
                level_text = style.replace("heading", "").strip()
                try:
                    level = int(level_text) if level_text else 1
                except ValueError:
                    level = 1
                if level <= len(current_headings):
                    current_headings = current_headings[:level - 1]
                current_headings = current_headings[:level - 1] + [text]
                passages.append(ExtractedPassage(text="", heading=current_headings[-1], section_path=" > ".join(current_headings)))
            continue
        if not text:
            continue
        passages.append(
            ExtractedPassage(
                text=text,
                section_path=" > ".join(current_headings) if current_headings else None,
                heading=current_headings[-1] if current_headings else None,
            )
        )
    merged: list[ExtractedPassage] = []
    pending_heading = None
    pending_section = None
    for p in passages:
        if not p.text:
            pending_heading = p.heading
            pending_section = p.section_path
            continue
        merged.append(
            ExtractedPassage(
                text=p.text,
                page_number=p.page_number,
                section_path=p.section_path or pending_section,
                heading=p.heading or pending_heading,
            )
        )
        pending_heading = None
        pending_section = None
    return ExtractedDocument(passages=merged, page_count=None, extractor="python-docx")


def _extract_text(data: bytes, *, markdown: bool) -> ExtractedDocument:
    text = data.decode("utf-8", errors="replace")
    if not markdown:
        return ExtractedDocument(passages=[ExtractedPassage(text=text)], page_count=None, extractor="utf-8")
    lines = text.splitlines()
    passages: list[ExtractedPassage] = []
    current: list[str] = []
    current_headings: list[str] = []

    def flush():
        nonlocal current
        body = "\n".join(current).strip()
        if body:
            passages.append(
                ExtractedPassage(
                    text=body,
                    section_path=" > ".join(current_headings) if current_headings else None,
                    heading=current_headings[-1] if current_headings else None,
                )
            )
        current = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#") and len(stripped) >= 2 and stripped[1] in (" ", "#", "\t"):
            flush()
            hashes = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped.lstrip("#").strip()
            if hashes <= len(current_headings):
                current_headings = current_headings[:max(hashes - 1, 0)]
            current_headings = current_headings[:hashes - 1] + [heading_text]
            continue
        current.append(line)
    flush()
    if not passages:
        passages.append(ExtractedPassage(text=text))
    return ExtractedDocument(passages=passages, page_count=None, extractor="markdown")


def chunk_passages(passages: Iterable[ExtractedPassage]) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for p in passages:
        text = (p.text or "").strip()
        if not text:
            continue
        blocks = text.split("\n\n") if "\n\n" in text else [text]
        buffer = ""
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            if buffer and len(buffer) + len(block) + 2 <= MAX_CHUNK_CHARS:
                buffer = buffer + "\n\n" + block
                continue
            if buffer:
                chunks.append(Chunk(content=buffer, chunk_index=idx,
                                   page_number=p.page_number, section_path=p.section_path, heading=p.heading))
                idx += 1
                buffer = ""
            if len(block) > MAX_CHUNK_CHARS:
                for i in range(0, len(block), MAX_CHUNK_CHARS):
                    piece = block[i:i + MAX_CHUNK_CHARS].strip()
                    if piece:
                        chunks.append(Chunk(content=piece, chunk_index=idx,
                                           page_number=p.page_number, section_path=p.section_path, heading=p.heading))
                        idx += 1
                buffer = ""
            else:
                buffer = block
        if buffer:
            chunks.append(Chunk(content=buffer, chunk_index=idx,
                               page_number=p.page_number, section_path=p.section_path, heading=p.heading))
            idx += 1
            buffer = ""
    for i, c in enumerate(chunks):
        c.chunk_index = i
    return chunks
