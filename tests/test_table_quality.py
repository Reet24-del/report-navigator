"""Geometry, not guessed digits, determines whether OCR recovery is usable."""

import pytest

from src.report_navigator.table_quality import (
    consistent_recovery,
    containing_band,
    line_centers,
    numeric_cells,
    remap_words,
)


def word(text, x0, x1, y=10):
    return (x0, y, x1, y + 8, text, 0, 0, 0)


COLUMNS = [0, 100, 150, 200]
GOOD = [word("North", 5, 30), word("73", 110, 125), word("91", 160, 175)]


def test_adjacent_pixels_form_one_physical_line():
    assert line_centers([1, 2, 3, 8, 9]) == [2, 8.5]


def test_merged_numeric_token_is_not_split():
    merged = word("7391", 110, 175)
    assert containing_band(merged, COLUMNS) is None
    assert numeric_cells([merged], COLUMNS) is None


def test_recovery_accepts_complete_geometry_and_unchanged_readings():
    original = [GOOD[0], word("7391", 110, 175)]
    assert consistent_recovery(original, GOOD, COLUMNS)


def test_conflicting_single_cell_value_is_rejected():
    original = [GOOD[0], word("74", 110, 125)]
    assert not consistent_recovery(original, GOOD, COLUMNS)


def test_missing_or_duplicate_columns_are_rejected():
    assert not consistent_recovery([], GOOD[:-1], COLUMNS)
    assert numeric_cells(GOOD + [word("18", 112, 125)], COLUMNS) is None


def test_text_and_year_header_is_not_a_recovered_body():
    header = [word("District", 5, 40), word("Killed", 105, 135), word("2034", 110, 130)]
    assert not consistent_recovery([], header, COLUMNS)


def test_crop_coordinates_map_to_original_page():
    mapped = remap_words([word("73", 20, 40, 8)], (100, 200), scale=2)[0]
    assert mapped[:4] == (110, 204, 120, 208)
    assert mapped[4] == "73"
    with pytest.raises(ValueError):
        remap_words(GOOD, (0, 0), scale=0)


def test_recovery_cannot_silently_replace_entity_label():
    original = [word("South", 5, 30), word("7391", 110, 175)]
    assert not consistent_recovery(original, GOOD, COLUMNS)
