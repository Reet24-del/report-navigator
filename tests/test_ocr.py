"""Exercise the actual installed OCR model plus bounded failure paths."""

import pymupdf
import pytest
from test_tables import make_grid_pdf

from backend import BackendError, Settings, load_report
from src.report_navigator.ocr import needs_ocr, recognize_page


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


@pytest.mark.parametrize("dense", [False, True])
def test_wrapped_entities_stay_in_physical_grid_row(tmp_path, dense):
    from scripts.benchmark_scans import make_case

    pdf, questions = make_case(wrapped=True, dense=dense)
    nav = load_report(pdf, "wrapped.pdf", settings=Settings(cache_dir=tmp_path))
    for question, expected in questions:
        result = nav.predict(question)
        assert result.answer == expected
        assert result.page == (None if expected == "NOT_FOUND" else 1)


def test_timeout_retains_completed_first_pass(monkeypatch):
    import json
    import subprocess
    from pathlib import Path

    def timeout(command, **kwargs):
        destination = Path(command[command.index("--worker-output") + 1])
        destination.write_text(
            json.dumps(
                {
                    "words": [[1, 2, 3, 4, "North", 0, 0, 0]],
                    "blocks": [[1, 2, 3, 4, "North", 0, 0]],
                }
            )
        )
        assert kwargs["timeout"] <= 2
        raise subprocess.TimeoutExpired(command, 2)

    monkeypatch.setattr("src.report_navigator.ocr.subprocess.run", timeout)
    with pymupdf.open(stream=make_grid_pdf(scanned=True), filetype="pdf") as doc:
        payload = recognize_page(doc[0], Settings(), 2)
    assert payload["recovery_timed_out"]
    assert payload["words"][0][4] == "North"


def test_real_crop_ocr_recovers_merged_first_pass_without_guessing():
    import time

    import numpy as np

    from scripts.benchmark_scans import make_case
    from src.report_navigator.ocr import recover_regions
    from src.report_navigator.table_quality import line_centers, numeric_cells

    pdf, _ = make_case(wrapped=True)
    settings = Settings()
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        page = doc[0]
        payload = recognize_page(page, settings, 25)
        pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csRGB, alpha=False)
        pixels = (
            np.frombuffer(pix.samples, dtype=np.uint8)
            .reshape(pix.height, pix.width, 3)
            .copy()
        )
        dark = pixels.mean(2) < 90
        rows = line_centers(np.flatnonzero(dark.mean(1) > 0.6))
        cols = line_centers(np.flatnonzero(dark.mean(0) > 0.3))
        row = [w for w in payload["words"] if 110 < (w[1] + w[3]) / 2 < 160]
        nums = [w for w in row if w[4].isdigit()]
        assert len(nums) == 3
        nums.sort(key=lambda w: w[0])
        # Fault injection simulates one first-pass token spanning two cells.
        merged = (
            nums[0][0],
            nums[0][1],
            nums[1][2],
            nums[0][3],
            nums[0][4] + nums[1][4],
            0,
            0,
            0,
        )
        original = [w for w in payload["words"] if w not in nums[:2]] + [merged]
        recovered, attempts = recover_regions(
            original,
            pixels,
            rows,
            cols,
            page.rect,
            str(settings.tessdata_dir),
            300,
            1,
            time.monotonic() + 10,
        )
        assert attempts == 1
        mapped_cols = [x / pix.width * page.rect.width for x in cols]
        recovered_row = [w for w in recovered if 110 < (w[1] + w[3]) / 2 < 160]
        assert numeric_cells(recovered_row, mapped_cols) == {
            1: "731",
            2: "83",
            3: "957",
        }
        unchanged, attempts = recover_regions(
            original,
            pixels,
            rows,
            cols,
            page.rect,
            str(settings.tessdata_dir),
            300,
            0,
            time.monotonic() + 10,
        )
        assert attempts == 0
        assert unchanged == original


def test_prose_evidence_uses_accepted_recovery_words():
    from src.report_navigator.ocr import blocks_from_words

    words = [
        (5, 10, 40, 20, "North", 0, 0, 0),
        (110, 10, 125, 20, "73", 0, 0, 0),
        (160, 10, 180, 20, "91", 0, 0, 0),
    ]
    blocks = blocks_from_words(words)
    assert len(blocks) == 1
    assert blocks[0][4] == "North 73 91"
    assert blocks[0][:4] == (5, 10, 180, 20)
    assert blocks_from_words([]) == []
