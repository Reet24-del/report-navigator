"""Generalized table logic tested with invented entities, years and values."""

import pymupdf
import pytest

from backend import Settings, load_report
from src.report_navigator.query import parse_question
from src.report_navigator.schemas import Chunk, TableCell, TableRow
from src.report_navigator.solver import solve


def table_chunk(label="North District", year="2027", killed="73", prefix="", page=1):
    cells = (
        TableCell(header=f"{prefix}Total Accidents | {year}", value="321"),
        TableCell(header=f"{prefix}Persons Killed | {year}", value=killed),
        TableCell(header=f"{prefix}Persons Killed | Ranking | {year}", value="1"),
        TableCell(header=f"{prefix}Persons Injured | {year}", value="455"),
    )
    row = TableRow(
        table_id="invented",
        title=f"Road accidents in districts during {year}",
        label=label,
        cells=cells,
    )
    return Chunk(
        chunk_id=f"doc:p{page}:r1",
        document_id="doc",
        pdf_page=page,
        text=f"{label}: accidents 321; killed {killed}; injured 455",
        table=row,
    )


@pytest.mark.parametrize(
    "question, expected",
    [
        ("How many people were killed in North District in 2027?", "73"),
        ("What was the number of accident deaths in North District during 2027?", "73"),
        ("How many accidents in North District in 2027?", "321"),
        ("How many people were injured in North District in 2027?", "455"),
        ("How many were killed in South District in 2027?", "NOT_FOUND"),
        ("How many were killed in North District in 2026?", "NOT_FOUND"),
        ("What percentage were killed in North District in 2027?", "NOT_FOUND"),
        ("How did deaths in North District change from 2026 to 2027?", "NOT_FOUND"),
    ],
)
def test_generalized_selection(question, expected):
    assert solve(question, (table_chunk(),)).answer == expected


def test_category_subtotal_cannot_replace_total():
    query = "How many people were killed in North District in 2027?"
    assert solve(query, (table_chunk(prefix="Others | "),)).answer == "NOT_FOUND"
    assert solve(query, (table_chunk(prefix="Others | "), table_chunk())).answer == "73"


def test_equally_supported_conflicting_counts_abstain():
    assert (
        solve(
            "How many people were killed in North District in 2027?",
            (table_chunk(), table_chunk(killed="81", page=2)),
        ).answer
        == "NOT_FOUND"
    )


def test_deaths_in_road_accidents_is_not_an_accident_count():
    chunk = table_chunk()
    cells = list(chunk.table.cells)
    cells[1] = cells[1].model_copy(
        update={"header": "Persons Killed in Road Accidents | 2027"}
    )
    altered = chunk.model_copy(
        update={"table": chunk.table.model_copy(update={"cells": tuple(cells)})}
    )
    assert (
        solve(
            "How many road accidents occurred in North District in 2027?", (altered,)
        ).answer
        == "321"
    )


def test_road_class_subtotal_does_not_answer_all_roads():
    chunk = table_chunk()
    subset = chunk.model_copy(
        update={
            "table": chunk.table.model_copy(
                update={"title": "Road accidents on NH during 2027"}
            )
        }
    )
    assert (
        solve(
            "How many people were killed in North District in 2027?", (subset,)
        ).answer
        == "NOT_FOUND"
    )


def test_no_year_guess_on_multi_year_table():
    row = table_chunk()
    altered = row.model_copy(
        update={
            "table": row.table.model_copy(
                update={
                    "cells": row.table.cells
                    + (TableCell(header="Persons Killed | 2028", value="98"),)
                }
            )
        }
    )
    assert (
        solve("How many people were killed in North District?", (altered,)).answer
        == "NOT_FOUND"
    )


def test_question_parsing_keeps_parenthetical_entity_and_ignores_trailing_year():
    query = parse_question(
        "How many two-wheeler riders were killed in Newtown (East) in 2028?"
    )
    assert query.entity == "newtown east"
    assert query.year == "2028"
    assert query.category == "two wheeler"


def make_grid_pdf(scanned=False):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=400)
        page.insert_text(
            (40, 40), "Road accidents in districts during 2027", fontsize=12
        )
        columns = [40, 220, 330, 440, 560]
        rows = [65, 105, 145, 185, 225]
        data = [
            ["District", "Accidents 2027", "Killed 2027", "Injured 2027"],
            ["North District", "321", "73", "455"],
            ["South District", "219", "31", "287"],
            ["West District", "137", "19", "156"],
        ]
        for y in rows:
            page.draw_line((columns[0], y), (columns[-1], y))
        for x in columns:
            page.draw_line((x, rows[0]), (x, rows[-1]))
        for r, row in enumerate(data):
            for c, text in enumerate(row):
                page.insert_text((columns[c] + 6, rows[r] + 24), text, fontsize=10)
        if not scanned:
            return document.tobytes()
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False)
        with pymupdf.open() as raster:
            target = raster.new_page(width=600, height=400)
            target.insert_image(target.rect, pixmap=pixmap)
            return raster.tobytes()


def test_native_pdf_row_retains_headers_and_coordinates(tmp_path):
    navigator = load_report(
        make_grid_pdf(), "invented.pdf", settings=Settings(cache_dir=tmp_path)
    )
    answer = navigator.predict("How many people were killed in North District in 2027?")
    assert answer.answer == "73"
    assert answer.source.table.label == "North District"
    assert answer.source.bboxes
    assert (
        navigator.ask("How many people were killed in North District in 2027?")
        .citations[0]
        .pdf_page
        == 1
    )


def test_ocr_grid_rejects_numeric_tokens_spanning_columns():
    from src.report_navigator.ocr import RecognizedPage
    from src.report_navigator.tables import extract_table_chunks

    words = [(10, 10, 40, 18, "Killed", 0, 0, 0)]
    for i in range(3):
        y = 35 + i * 30
        words += [
            (5, y, 70, y + 8, "North", 0, 0, 0),
            (110, y, 175, y + 8, "7391", 0, 0, 0),
            (210, y, 225, y + 8, "88", 0, 0, 0),
        ]
    with pymupdf.open() as document:
        page = document.new_page(width=250, height=130)
        recognized = RecognizedPage(
            page,
            {
                "words": words,
                "blocks": [],
                "grid_rows": [0, 25, 55, 85, 115],
                "grid_columns": [0, 100, 150, 200, 250],
            },
        )
        assert extract_table_chunks(recognized, "synthetic", "ocr") == []


def test_recovery_settings_invalidate_report_cache():
    from src.report_navigator.storage import extraction_settings

    assert extraction_settings(Settings()) != extraction_settings(
        Settings(ocr_recovery_enabled=False)
    )
    assert extraction_settings(Settings()) != extraction_settings(
        Settings(ocr_max_regions=0)
    )
