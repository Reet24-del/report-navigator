"""Exercise the actual installed OCR model plus bounded failure paths."""

import pymupdf
import pytest
from backend import BackendError, Settings, load_report
from src.report_navigator.ocr import needs_ocr, recognize_page
from test_tables import make_grid_pdf


def test_rasterized_table_is_searchable_and_answerable(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    assert (settings.tessdata_dir / "eng.traineddata").is_file(), (
        "Install the declared OCR asset before testing."
    )
    navigator = load_report(make_grid_pdf(scanned=True), "scan.pdf", settings=settings)
    assert navigator.report_info.ocr_pages == 1
    assert all(chunk.extraction_method == "ocr" for chunk in navigator._index.chunks)
    assert (
        navigator.predict(
            "How many people were killed in North District in 2027?"
        ).answer
        == "73"
    )


def test_missing_model_has_clear_failure(tmp_path):
    settings = Settings(tessdata_dir=tmp_path)
    with pymupdf.open(stream=make_grid_pdf(scanned=True), filetype="pdf") as document:
        with pytest.raises(BackendError) as caught:
            recognize_page(document[0], settings, 10)
    assert caught.value.code == "ocr_unavailable"


def test_ocr_timeout_is_bounded(tmp_path, monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr("src.report_navigator.ocr.subprocess.run", timeout)
    with pymupdf.open(stream=make_grid_pdf(scanned=True), filetype="pdf") as document:
        with pytest.raises(BackendError) as caught:
            recognize_page(document[0], Settings(), 1)
    assert caught.value.code == "ocr_timeout"


def test_native_table_does_not_require_ocr():
    with pymupdf.open(stream=make_grid_pdf(), filetype="pdf") as document:
        page = document[0]
        assert not needs_ocr(page, page.get_text(), Settings())


def test_scanned_multilevel_headers_select_the_requested_year(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=400)
        page.insert_text(
            (40, 38), "Road accidents in districts during 2030 and 2031", fontsize=12
        )
        columns = [40, 190, 250, 310, 370, 430, 490, 550]
        for y in [65, 95, 125, 165, 205, 245]:
            page.draw_line((40, y), (550, y))
        for x in columns:
            page.draw_line((x, 65), (x, 245))
        for x, label in [(200, "Accidents"), (320, "Killed"), (440, "Injured")]:
            page.insert_text((x, 86), label, fontsize=10)
        for index in range(6):
            page.insert_text(
                (columns[index + 1] + 5, 116), str(2030 + index % 2), fontsize=10
            )
        rows = [
            ["East District", "801", "902", "17", "23", "110", "135"],
            ["West District", "501", "612", "11", "19", "71", "83"],
            ["South District", "401", "512", "13", "21", "65", "91"],
        ]
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                page.insert_text((columns[c] + 5, 151 + r * 40), value, fontsize=10)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False)
        with pymupdf.open() as scan:
            target = scan.new_page(width=600, height=400)
            target.insert_image(target.rect, pixmap=pixmap)
            pdf = scan.tobytes()
    navigator = load_report(
        pdf, "multi-scan.pdf", settings=Settings(cache_dir=tmp_path)
    )
    assert (
        navigator.predict(
            "How many people were killed in East District in 2031?"
        ).answer
        == "23"
    )
    assert (
        navigator.predict(
            "How many people were killed in East District in 2030?"
        ).answer
        == "17"
    )
    assert (
        navigator.predict(
            "How many people were killed in East District in 2032?"
        ).answer
        == "NOT_FOUND"
    )
