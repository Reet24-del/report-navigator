"""Native PDF extraction and page-preserving, paragraph-aware chunking."""

import hashlib
import time
from pathlib import Path

import pymupdf

from .config import Settings
from .ocr import RecognizedPage, needs_ocr, recognize_page
from .schemas import BackendError, Chunk, ReportInfo
from .tables import extract_table_chunks


def document_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def validate_pdf(pdf_bytes: bytes, settings: Settings) -> int:
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
        raise BackendError("invalid_pdf", "Upload a non-empty PDF file.")
    if len(pdf_bytes) > settings.max_pdf_bytes:
        raise BackendError(
            "pdf_too_large", "The PDF exceeds the configured upload limit."
        )
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            if document.needs_pass:
                raise BackendError(
                    "encrypted_pdf", "Upload an unlocked copy of the PDF."
                )
            count = len(document)
            if not count or count > settings.max_pages:
                raise BackendError(
                    "page_limit", "The PDF has no pages or exceeds the page limit."
                )
            return count
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise BackendError(
            "invalid_pdf", "This file could not be read as a PDF."
        ) from None


def _page_chunks(
    page, document_id: str, settings: Settings, method="native"
) -> list[Chunk]:
    blocks = [
        block
        for block in page.get_text("blocks", sort=True)
        if block[6] == 0 and block[4].strip()
    ]
    words: list[tuple[str, int]] = []
    boundaries: list[int] = []
    for block_index, block in enumerate(blocks):
        words.extend((word, block_index) for word in block[4].split())
        boundaries.append(len(words))
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + settings.chunk_words, len(words))
        if end < len(words):
            candidates = [
                boundary
                for boundary in boundaries
                if start + settings.chunk_words * 0.75 <= boundary <= end
            ]
            if candidates:
                end = candidates[-1]
        selected = words[start:end]
        block_ids = list(dict.fromkeys(block_id for _, block_id in selected))
        chunks.append(
            Chunk(
                chunk_id=f"{document_id}:p{page.number + 1}:c{len(chunks) + 1}",
                document_id=document_id,
                pdf_page=page.number + 1,
                page_label=page.get_label() or None,
                text=" ".join(word for word, _ in selected),
                bboxes=tuple(tuple(blocks[index][:4]) for index in block_ids),
                extraction_method=method,
            )
        )
        if end == len(words):
            break
        start = max(start + 1, end - settings.overlap_words)
    return chunks


def extract_pdf(
    pdf_bytes: bytes, filename: str, settings: Settings, deadline: float | None = None
) -> tuple[ReportInfo, tuple[Chunk, ...]]:
    page_count = validate_pdf(pdf_bytes, settings)
    document_id = document_hash(pdf_bytes)
    chunks: list[Chunk] = []
    unprocessed = []
    ocr_pages = 0
    warnings = []
    deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + settings.runtime_seconds
    )
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        for page in document:
            if time.monotonic() >= deadline:
                unprocessed.extend(range(page.number + 1, page_count + 1))
                warnings.append(
                    "Document ingestion reached its time budget; remaining pages were not indexed."
                )
                break
            try:
                text = page.get_text("text", sort=True)
                source_page = page
                method = "native"
                if needs_ocr(page, text, settings):
                    if not settings.ocr_enabled:
                        unprocessed.append(page.number + 1)
                        continue
                    try:
                        payload = recognize_page(
                            page, settings, deadline - time.monotonic()
                        )
                        source_page = RecognizedPage(page, payload)
                        if payload.get("recovery_timed_out"):
                            warnings.append(
                                f"Page {page.number + 1}: optional OCR recovery timed out; the completed first pass was retained."
                            )
                        if payload.get("recovery_attempted"):
                            warnings.append(
                                f"Page {page.number + 1}: selective OCR row recovery was attempted; ambiguous readings remain unsupported."
                            )
                        text = " ".join(word[4] for word in payload["words"])
                        method = "ocr"
                    except BackendError as error:
                        warnings.append(f"Page {page.number + 1}: {error.message}")
                        unprocessed.append(page.number + 1)
                        continue
                useful_chars = sum(char.isalnum() for char in text)
                broken_encoding = text.count("\ufffd") > max(2, len(text) * 0.05)
                if useful_chars < settings.min_native_chars or broken_encoding:
                    unprocessed.append(page.number + 1)
                else:
                    chunks.extend(
                        _page_chunks(source_page, document_id, settings, method)
                    )
                    chunks.extend(
                        extract_table_chunks(source_page, document_id, method)
                    )
                    ocr_pages += method == "ocr"
            except (RuntimeError, ValueError):
                unprocessed.append(page.number + 1)
    if not chunks:
        raise BackendError(
            "no_searchable_text",
            "No usable text was extracted. Check OCR availability and PDF readability.",
        )
    if unprocessed:
        warnings.append(
            "Some pages have insufficient or unusable text and were not indexed. Inspect processing coverage."
        )
    info = ReportInfo(
        document_id=document_id,
        filename=Path(filename).name or "report.pdf",
        page_count=page_count,
        searchable_pages=len({chunk.pdf_page for chunk in chunks}),
        ocr_pages=ocr_pages,
        unprocessed_pages=tuple(unprocessed),
        warnings=tuple(dict.fromkeys(warnings)),
    )
    return info, tuple(chunks)
