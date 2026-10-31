"""Versioned JSON cache. Failed or mismatched caches are rebuilt from the PDF."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pymupdf
from pydantic import ValidationError

from .config import Settings
from .schemas import Chunk, ReportInfo

CACHE_VERSION = 2


def extraction_settings(settings: Settings) -> dict:
    return {
        "cache_version": CACHE_VERSION,
        "chunk_words": settings.chunk_words,
        "overlap_words": settings.overlap_words,
        "min_native_chars": settings.min_native_chars,
        "ocr_enabled": settings.ocr_enabled,
        "ocr_dpi": settings.ocr_dpi,
        "ocr_recovery_enabled": settings.ocr_recovery_enabled,
        "ocr_max_regions": settings.ocr_max_regions,
        "ocr_model": _ocr_model_hash(settings),
        "parser_version": pymupdf.VersionBind,
        "table_revision": 4,
        "ocr_revision": 4,
    }


def _ocr_model_hash(settings):
    model = settings.tessdata_dir / "eng.traineddata"
    if not settings.ocr_enabled or not model.is_file():
        return None
    return hashlib.sha256(model.read_bytes()).hexdigest()


def _directory(document_id: str, settings: Settings) -> Path:
    fingerprint = hashlib.sha256(
        json.dumps(extraction_settings(settings), sort_keys=True).encode()
    ).hexdigest()[:16]
    return settings.cache_dir / document_id / fingerprint


def _atomic_write(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_cache(document_id: str, page_count: int, filename: str, settings: Settings):
    cache_file = _directory(document_id, settings) / "chunks.json"
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if payload["settings"] != extraction_settings(settings):
            return None
        info = ReportInfo.model_validate(payload["report_info"])
        chunks = tuple(Chunk.model_validate(item) for item in payload["chunks"])
        pages = {chunk.pdf_page for chunk in chunks}
        if (
            info.document_id != document_id
            or info.page_count != page_count
            or not chunks
            or any(
                chunk.document_id != document_id or chunk.pdf_page > page_count
                for chunk in chunks
            )
            or len({chunk.chunk_id for chunk in chunks}) != len(chunks)
            or len(pages) != info.searchable_pages
            or pages.intersection(info.unprocessed_pages)
            or pages.union(info.unprocessed_pages) != set(range(1, page_count + 1))
        ):
            return None
        return info.model_copy(update={"filename": filename}), chunks
    except (OSError, ValueError, TypeError, KeyError, ValidationError):
        return None


def write_cache(
    pdf_bytes: bytes, info: ReportInfo, chunks: tuple[Chunk, ...], settings: Settings
) -> None:
    directory = _directory(info.document_id, settings)
    payload = {
        "settings": extraction_settings(settings),
        "report_info": info.model_dump(mode="json"),
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
    }
    _atomic_write(directory / "report.pdf", pdf_bytes)
    # Settings, metadata and chunks share one atomic snapshot.
    _atomic_write(
        directory / "chunks.json",
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
