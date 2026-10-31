"""Document correctness checks using real PDFs generated in memory."""

import json

import pymupdf
import pytest
from backend import BackendError, Settings, load_report
from src.report_navigator.ingest import extract_pdf
from src.report_navigator.retrieval import build_index, retrieve


def make_pdf(pages):
    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_textbox(pymupdf.Rect(40, 40, 550, 780), text, fontsize=11)
        return document.tobytes()


def test_physical_pages_labels_and_source_rectangles(tmp_path):
    pdf = make_pdf(
        [
            "This statistical report describes agricultural household survey results for 2020.",
            "District Aurangabad recorded 125 participating households in the year 2023.",
        ]
    )
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        document.set_page_labels(
            [{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1}]
        )
        pdf = document.tobytes()
    info, chunks = extract_pdf(pdf, "sample.pdf", Settings(cache_dir=tmp_path))
    match = retrieve("Aurangabad households 2023", build_index(chunks))[0]
    assert info.searchable_pages == 2
    assert match.pdf_page == 2
    assert match.page_label == "ii"
    assert match.bboxes and all(
        box[2] > box[0] and box[3] > box[1] for box in match.bboxes
    )


def test_chunking_preserves_all_words_and_stays_on_page(tmp_path):
    text = " ".join(f"term{index}" for index in range(180))
    _, chunks = extract_pdf(
        make_pdf(
            [
                text,
                "A second page contains entirely separate survey evidence and coverage statistics.",
            ]
        ),
        "long.pdf",
        Settings(cache_dir=tmp_path, chunk_words=50, overlap_words=10),
    )
    first_page = [chunk for chunk in chunks if chunk.pdf_page == 1]
    observed = {word for chunk in first_page for word in chunk.text.split()}
    assert observed == set(text.split())
    assert len(first_page) > 1
    assert all(len(chunk.text.split()) <= 50 for chunk in chunks)
    assert "term" not in " ".join(chunk.text for chunk in chunks if chunk.pdf_page == 2)


def test_single_chunk_retrieval_and_unmatched_question(tmp_path):
    navigator = load_report(
        make_pdf(
            [
                "The district survey recorded 125 households participating in agriculture in 2023."
            ]
        ),
        "one.pdf",
        settings=Settings(cache_dir=tmp_path),
    )
    assert retrieve("households 2023", navigator._index)
    assert not retrieve("volcanoes", navigator._index)


def test_blank_page_is_reported_and_empty_report_rejected(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    info, _ = extract_pdf(
        make_pdf(
            [
                "This page contains a readable statistical summary of district employment.",
                "",
            ]
        ),
        "mixed.pdf",
        settings,
    )
    assert info.unprocessed_pages == (2,)
    assert info.warnings
    with pytest.raises(BackendError, match="OCR") as caught:
        load_report(make_pdf([""]), "empty.pdf", settings=settings)
    assert caught.value.code == "no_searchable_text"


def test_scan_with_selectable_header_is_not_mistaken_for_body_text(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page()
        # A blank raster represents an unreadable scanned body for this routing check.
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
        pixmap.clear_with(255)
        page.insert_image(page.rect, pixmap=pixmap)
        page.insert_text(
            (40, 40),
            "Government statistical report section heading and printed page number",
        )
        pdf = document.tobytes()
    with pytest.raises(BackendError) as caught:
        load_report(
            pdf, "scan.pdf", settings=Settings(cache_dir=tmp_path, ocr_enabled=False)
        )
    assert caught.value.code == "no_searchable_text"


@pytest.mark.parametrize("content", [b"", b"not a PDF", b"%PDF-1.7\ntruncated"])
def test_corrupt_pdfs_are_actionable(content, tmp_path):
    with pytest.raises(BackendError) as caught:
        load_report(content, "bad.pdf", settings=Settings(cache_dir=tmp_path))
    assert caught.value.code == "invalid_pdf"


def test_encrypted_pdf_is_rejected(tmp_path):
    with pymupdf.open(
        stream=make_pdf(
            ["A report with private locked content and sufficient native text."]
        ),
        filetype="pdf",
    ) as document:
        pdf = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader"
        )
    with pytest.raises(BackendError) as caught:
        load_report(pdf, "locked.pdf", settings=Settings(cache_dir=tmp_path))
    assert caught.value.code == "encrypted_pdf"


def test_corrupt_cache_rebuild_and_settings_invalidation(tmp_path):
    pdf = make_pdf(
        [
            "The survey describes irrigation coverage for agricultural households in 2023."
        ]
    )
    settings = Settings(cache_dir=tmp_path)
    first = load_report(pdf, "first.pdf", settings=settings)
    cache = next(tmp_path.rglob("chunks.json"))
    payload = json.loads(cache.read_text())
    payload["chunks"][0]["document_id"] = "wrong-document"
    cache.write_text(json.dumps(payload))
    second = load_report(pdf, "renamed.pdf", settings=settings)
    assert second.report_info.filename == "renamed.pdf"
    assert second._index.chunks[0].document_id == first.report_info.document_id
    load_report(
        pdf, "third.pdf", settings=settings.model_copy(update={"chunk_words": 200})
    )
    assert len(list(tmp_path.rglob("chunks.json"))) == 2


def test_cache_hit_avoids_reextraction(tmp_path, monkeypatch):
    import src.report_navigator.service as service

    pdf = make_pdf(
        [
            "The survey describes irrigation coverage for agricultural households in 2023."
        ]
    )
    settings = Settings(cache_dir=tmp_path)
    load_report(pdf, "first.pdf", settings=settings)

    def unexpected_extraction(*args):
        raise AssertionError("A valid cache should avoid reextraction")

    monkeypatch.setattr(service, "extract_pdf", unexpected_extraction)
    assert (
        load_report(pdf, "second.pdf", settings=settings).report_info.filename
        == "second.pdf"
    )


def test_upload_limit_is_applied_before_cache_use(tmp_path):
    pdf = make_pdf(
        ["This report includes district coverage and sufficient readable native text."]
    )
    settings = Settings(cache_dir=tmp_path)
    load_report(pdf, "report.pdf", settings=settings)
    with pytest.raises(BackendError) as caught:
        load_report(
            pdf,
            "report.pdf",
            settings=settings.model_copy(update={"max_pdf_bytes": 10}),
        )
    assert caught.value.code == "pdf_too_large"
