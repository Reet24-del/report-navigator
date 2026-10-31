"""Rows retain their merged column headings and original cell coordinates."""

import re
from statistics import median

from .schemas import Chunk, TableCell, TableRow
from .table_quality import numeric_cells

NUMBER = re.compile(
    r"^(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3})(?:\.\d+)?%?$"
)
YEAR = re.compile(r"^(?:19|20)\d{2}$")


def _clean(value) -> str:
    return " ".join((value or "").split())


def _body_start(rows: list[list[str | None]]) -> int | None:
    for index, row in enumerate(rows):
        texts = [_clean(cell) for cell in row]
        numbers = [text for text in texts if NUMBER.fullmatch(text)]
        labels = [text for text in texts if re.search(r"[A-Za-z]", text)]
        if (
            len(numbers) >= 2
            and labels
            and any(not YEAR.fullmatch(number) for number in numbers)
        ):
            return index
    return None


def _title(page, bbox, textpage=None) -> str:
    # Title and section text above a table are relevant context, not answer data.
    blocks = page.get_text("blocks", textpage=textpage, sort=True)
    above = [
        _clean(block[4])
        for block in blocks
        if block[6] == 0 and block[3] <= bbox[1] + 2
    ]
    captions = [
        index
        for index, text in enumerate(above)
        if re.match(r"(?:table\s+\d|annexure\s+\d)", text, re.I)
    ]
    if captions:
        return " ".join(above[captions[-1] :])[:1600]
    return " ".join(above)[-1600:]


def _headers(table, rows, start):
    headers = [[] for _ in range(table.col_count)]
    for row_index in range(start):
        row = rows[row_index]
        # Merged cells inherit labels only across their physical merged span.
        current = ""
        for column, value in enumerate(row):
            rectangle = table.rows[row_index].cells[column]
            if value is not None:
                current = _clean(value)
            elif rectangle is not None:
                current = ""
            if current and current not in headers[column]:
                headers[column].append(current)
    return [" | ".join(parts) for parts in headers]


def extract_table_chunks(
    page, document_id: str, method="native", textpage=None
) -> list[Chunk]:
    chunks = []
    # Coloured cell backgrounds carry the row grid in many official reports.
    finder = page.find_tables(strategy="lines") if method == "native" else None
    for table_index, table in enumerate(finder.tables if finder else []):
        rows = table.extract()
        start = _body_start(rows)
        if start is None or table.row_count - start < 2:
            continue
        headers = _headers(table, rows, start)
        title = _title(page, table.bbox, textpage)
        for row_index in range(start, len(rows)):
            values = [_clean(value) for value in rows[row_index]]
            labels = [
                value
                for value in values
                if value
                and re.search(r"[A-Za-z]", value)
                and not NUMBER.fullmatch(value)
            ]
            numeric_count = sum(bool(NUMBER.fullmatch(value)) for value in values)
            if not labels or numeric_count < 2:
                continue
            label = " ".join(labels)
            cells = tuple(
                TableCell(
                    header=headers[column],
                    value=value,
                    bbox=tuple(table.rows[row_index].cells[column])
                    if table.rows[row_index].cells[column]
                    else None,
                )
                for column, value in enumerate(values)
                if value
            )
            row = TableRow(
                table_id=f"p{page.number + 1}:t{table_index + 1}",
                title=title,
                label=label,
                cells=cells,
            )
            text = f"{title}\nRow: {label}\n" + "\n".join(
                f"{cell.header}: {cell.value}" for cell in cells
            )
            rectangles = tuple(cell.bbox for cell in cells if cell.bbox)
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}:p{page.number + 1}:t{table_index + 1}:r{row_index}",
                    document_id=document_id,
                    pdf_page=page.number + 1,
                    page_label=page.get_label() or None,
                    text=text,
                    bboxes=rectangles,
                    extraction_method=method,
                    table=row,
                )
            )
    if not chunks:
        chunks = _aligned_rows(page, document_id, method, textpage)
    return chunks


def _aligned_rows(page, document_id, method, textpage):
    """Conservative positional fallback for borderless/OCR tables."""
    words = page.get_text("words", textpage=textpage, sort=True)
    if not words:
        return []
    height = median(word[3] - word[1] for word in words)
    lines = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        center = (word[1] + word[3]) / 2
        if lines and abs(center - lines[-1][0]) < height * 0.45:
            lines[-1][1].append(word)
        else:
            lines.append((center, [word]))
    grid_columns = getattr(page, "grid_columns", [])
    grid_rows = getattr(page, "grid_rows", [])
    if len(grid_columns) >= 4 and len(grid_rows) >= 4:
        # Physical row boundaries keep wrapped entity labels with their values.
        lines = [
            (
                (top + bottom) / 2,
                [w for w in words if top <= (w[1] + w[3]) / 2 < bottom],
            )
            for top, bottom in zip(grid_rows, grid_rows[1:])
        ]
        outside = [w for w in words if (w[1] + w[3]) / 2 < grid_rows[0]]
        if outside:
            lines.insert(0, (grid_rows[0] - height, outside))
    candidate_rows = []
    for center, line in lines:
        line = sorted(line, key=lambda w: w[0])
        first_label = next(
            (i for i, word in enumerate(line) if re.search(r"[A-Za-z]", word[4])), None
        )
        if first_label is None:
            continue
        first_number = next(
            (
                i
                for i in range(first_label + 1, len(line))
                if NUMBER.fullmatch(line[i][4])
            ),
            None,
        )
        if first_number is None:
            continue
        values = [word for word in line[first_number:] if NUMBER.fullmatch(word[4])]
        if grid_columns:
            cells = numeric_cells(values, grid_columns)
            if cells is None or set(cells) != set(range(1, len(grid_columns) - 1)):
                continue
        if len(values) >= 2 and not all(YEAR.fullmatch(word[4]) for word in values):
            candidate_rows.append(
                (
                    center,
                    " ".join(
                        word[4]
                        for word in sorted(
                            line[first_label:first_number],
                            key=lambda w: (round((w[1] + w[3]) / max(height, 1)), w[0]),
                        )
                    ),
                    values,
                )
            )
    if len(candidate_rows) < 3:
        return []
    first_y = candidate_rows[0][0]
    above = [(y, line) for y, line in lines if y < first_y - height / 2]
    title = " ".join(
        word[4] for _, line in above for word in sorted(line, key=lambda w: w[0])
    )[-1600:]
    header_lines = [
        (y, line)
        for y, line in above
        if (not grid_rows or y >= grid_rows[0])
        and y > first_y - 9 * height
        and not re.match(
            r"(?:table|annexure)\s+\d",
            " ".join(w[4] for w in sorted(line, key=lambda w: w[0])),
            re.IGNORECASE,
        )
        and not (
            re.search(r"\b(?:and|to|over)\b", " ".join(w[4] for w in line))
            and re.fullmatch(
                r"(?:(?:19|20)\d{2}|and|to|over|\s)+", " ".join(w[4] for w in line)
            )
        )
    ]
    chunks = []
    for row_number, (_, label, values) in enumerate(candidate_rows):
        cells = []
        centers = [(word[0] + word[2]) / 2 for word in values]
        for column, word in enumerate(values):
            left = (
                (centers[column - 1] + centers[column]) / 2 if column else word[0] - 20
            )
            right = (
                (centers[column] + centers[column + 1]) / 2
                if column + 1 < len(values)
                else word[2] + 20
            )
            labels = []
            for _, header_words in header_lines:
                ordered = sorted(header_words, key=lambda w: w[0])
                year_words = []
                for item in ordered:
                    matches = list(re.finditer(r"(?:19|20)\d{2}", item[4]))
                    for match in matches:
                        # OCR sometimes attaches punctuation to a year token.
                        center = item[0] + (match.start() + 2) / max(
                            1, len(item[4])
                        ) * (item[2] - item[0])
                        year_words.append((match.group(), center))
                if len(year_words) >= 3 and len(year_words) / len(ordered) >= 0.6:
                    labels.extend(
                        year for year, center in year_words if left <= center < right
                    )
                    continue
                if all(NUMBER.fullmatch(w[4]) for w in ordered):
                    # Year rows map to columns; ordinal column numbers add no meaning.
                    labels.extend(
                        w[4]
                        for w in ordered
                        if YEAR.fullmatch(w[4]) and left <= (w[0] + w[2]) / 2 < right
                    )
                    continue
                groups = []
                for header_word in ordered:
                    if not groups or header_word[0] - groups[-1][-1][2] > max(
                        10, height * 1.5
                    ):
                        groups.append([header_word])
                    else:
                        groups[-1].append(header_word)
                if groups:
                    # Merged labels span multiple data columns: nearest label group
                    # supplies the parent heading, while the year line remains exact.
                    group = min(
                        groups,
                        key=lambda g: abs((g[0][0] + g[-1][2]) / 2 - centers[column]),
                    )
                    labels.append(" ".join(w[4] for w in group))
            cells.append(
                TableCell(
                    header=" | ".join(labels), value=word[4], bbox=tuple(word[:4])
                )
            )
        row = TableRow(
            table_id=f"p{page.number + 1}:aligned",
            title=title,
            label=label,
            cells=tuple(cells),
        )
        text = f"{title}\nRow: {label}\n" + "\n".join(
            f"{cell.header}: {cell.value}" for cell in cells
        )
        chunks.append(
            Chunk(
                chunk_id=f"{document_id}:p{page.number + 1}:a{row_number}",
                document_id=document_id,
                pdf_page=page.number + 1,
                page_label=page.get_label() or None,
                text=text,
                bboxes=tuple(cell.bbox for cell in cells),
                extraction_method=method,
                table=row,
            )
        )
    return chunks
