"""Conservative geometry checks; never infer missing digits from a table answer."""

import re

NUMERIC = re.compile(r"^(?:\d[\d,]*)(?:\.\d+)?%?$")


def line_centers(indices):
    """Collapse adjacent raster pixels belonging to one physical grid line."""
    groups = []
    for value in indices:
        if not groups or value > groups[-1][-1] + 1:
            groups.append([int(value)])
        else:
            groups[-1].append(int(value))
    return [sum(group) / len(group) for group in groups]


def containing_band(word, boundaries, tolerance=1.5):
    """A token must fit one cell; a token spanning two columns is ambiguous."""
    for index, (left, right) in enumerate(zip(boundaries, boundaries[1:])):
        if word[0] >= left - tolerance and word[2] <= right + tolerance:
            return index
    return None


def numeric_cells(words, columns):
    cells = {}
    for word in words:
        if not NUMERIC.fullmatch(word[4]):
            continue
        column = containing_band(word, columns)
        if column is None or column == 0 or column in cells:
            return None
        cells[column] = word[4]
    return cells


def data_band(words, columns):
    """Recognize a grid body row, excluding multi-line text/year headers."""
    label = [w for w in words if containing_band(w, columns) == 0]
    rest = [w for w in words if containing_band(w, columns) != 0]
    return bool(
        any(re.search(r"[A-Za-z]", w[4]) for w in label)
        and any(NUMERIC.fullmatch(w[4]) for w in rest)
        and not any(re.search(r"[A-Za-z]", w[4]) for w in rest)
    )


def consistent_recovery(original, recovered, columns):
    """Accept complete geometry only, preserving every unambiguous old reading."""
    cells = numeric_cells(recovered, columns)
    if not data_band(recovered, columns) or cells is None:
        return False
    if set(cells) != set(range(1, len(columns) - 1)):
        return False
    old_label = {
        w[4].strip(".,:;()").lower()
        for w in original
        if containing_band(w, columns) == 0
    }
    new_label = {
        w[4].strip(".,:;()").lower()
        for w in recovered
        if containing_band(w, columns) == 0
    }
    if old_label and old_label != new_label:
        return False
    # A merged token is unusable, but stable original single-cell readings
    # cannot be silently overridden by a second OCR pass.
    for word in original:
        column = containing_band(word, columns)
        if column and NUMERIC.fullmatch(word[4]) and cells.get(column) != word[4]:
            return False
    return True


def remap_words(words, origin, scale=1.0):
    """Map crop-page OCR coordinates into the original physical PDF page."""
    if scale <= 0:
        raise ValueError("Scale must be positive")
    x, y = origin
    return [
        (w[0] / scale + x, w[1] / scale + y, w[2] / scale + x, w[3] / scale + y, *w[4:])
        for w in words
    ]
