"""Offline cell selection. Never return the first number from a retrieved page."""

import re

from .query import normalize, parse_question
from .schemas import Chunk, NumericAnswer
from .tables import NUMBER

MEASURES = {
    "killed": {"killed", "deaths", "fatalities", "fatality"},
    "injured": {"injured", "injuries", "injury"},
    "accidents": {"accident", "accidents"},
}


def _abstain(reason: str, confidence=0.65):
    return NumericAnswer(answer="NOT_FOUND", confidence=confidence, reason=reason)


def _measure(text: str) -> str | None:
    killed = bool(re.search(r"\b(killed|deaths|fatalities|fatality)\b", text))
    injured = bool(re.search(r"\b(injured|injury|injuries)\b", text))
    if killed and injured:
        return None
    if killed:
        return "killed"
    if injured:
        return "injured"
    return "accidents" if re.search(r"\baccidents?\b", text) else None


def _header_matches_measure(header: str, context: str, measure: str) -> bool:
    explicit = _measure(normalize(header))
    if explicit is not None:
        return explicit == measure
    parts = [normalize(part) for part in header.split("|")]
    metadata_only = (
        parts
        and (
            bool(re.fullmatch(r"(?:19|20)\d{2}", parts[0]))
            or parts[0] in {"number", "total"}
        )
        and all(part.isdigit() or part in {"number", "total"} for part in parts)
    )
    return bool(metadata_only and _measure(context) == measure)


def solve(question: str, candidates: tuple[Chunk, ...]) -> NumericAnswer:
    query = parse_question(question)
    if not query.supported or not query.measure or not query.entity:
        return _abstain(
            "Question lacks a supported single-count entity/measure constraint.", 0.5
        )
    entity = set(normalize(query.entity).split())
    selected = []
    for rank, chunk in enumerate(candidates):
        row = chunk.table
        if row is None:
            continue
        label = set(normalize(row.label).split())
        # Geography/entity matches must be complete, not just a shared word.
        if not entity.issubset(label):
            continue
        context = normalize(row.title)
        question_text = normalize(question)
        if query.scope == "city" and not re.search(
            r"\b(cit(?:y|ies)|million plus)\b", context
        ):
            continue
        if query.scope == "national" and re.search(
            r"\b(cities|city wise|state wise|states uts)\b", context
        ):
            continue
        # A road-class subtotal cannot answer a question about all roads.
        if any(
            qualifier in context and qualifier not in question_text
            for qualifier in (
                "national highways",
                "state highways",
                "other roads",
                "expressways",
                "under nhai",
            )
        ):
            continue
        if query.scope == "national" and "million plus" in context:
            continue
        if query.topic == "collision" and not re.search(
            r"\b(collision|nature of accident)\b", context
        ):
            continue
        if query.topic == "road_user" and "road user" not in context:
            continue
        table_years = set(re.findall(r"\b(?:19|20)\d{2}\b", context))
        for cell in row.cells:
            raw = cell.value.strip()
            if not NUMBER.fullmatch(raw) or "." in raw or "%" in raw:
                continue
            header = normalize(cell.header)
            terms = set(header.split())
            if not _header_matches_measure(cell.header, context, query.measure):
                continue
            if re.search(r"\b(rank|ranking|share|percentage|percent|change)\b", header):
                continue
            if re.search(r"\b(per lakh|per 10|per 100|per 1000|per 10000)\b", header):
                continue
            if (
                query.measure == "accidents"
                and re.search(r"\bfatal\b", header + " " + context)
                and "fatal" not in question_text
            ):
                continue
            if not query.category and query.topic is None:
                first = normalize(cell.header.split("|")[0])
                if (
                    not set(first.split()).intersection(MEASURES[query.measure])
                    and first not in {"total", "number", "numbers", query.year}
                    and not re.fullmatch(r"(?:19|20)\d{2}", first)
                ):
                    continue
            years = set(re.findall(r"\b(?:19|20)\d{2}\b", header))
            if query.year:
                if years and years != {query.year}:
                    continue
                if not years and table_years != {query.year}:
                    continue
            if query.category:
                category = set(normalize(query.category).split())
                # National category questions name a row, city breakdowns name a column.
                category_context = set((header + " " + normalize(row.label)).split())
                if not category.issubset(category_context):
                    continue
            elif query.topic is None:
                # A total must not silently become a category-specific count.
                if re.search(
                    r"\b(pedestrian|two wheeler|bicycle|overspeeding|drunken|helmet|seat belt)\b",
                    header + " " + context,
                ):
                    continue
            if (
                query.measure == "injured"
                and re.search(r"\b(minor|grievously|seriously)\b", header)
                and "total" not in terms
            ):
                continue
            score = (
                10 + (4 if entity == label else 0) + (3 if query.year in years else 0)
            )
            score += 2 if "number" in terms or "numbers" in terms else 0
            if chunk.extraction_method == "ocr":
                score -= 2
            selected.append((score, rank, raw.replace(",", ""), chunk))
    if not selected:
        return _abstain(
            "No cell satisfies the requested entity, measure, year and category."
        )
    selected.sort(key=lambda item: (-item[0], item[1], item[3].pdf_page))
    best_score = selected[0][0]
    strongest = [item for item in selected if item[0] >= best_score - 1]
    values = {item[2] for item in strongest}
    if len(values) > 1:
        return _abstain(
            "Equally supported cells disagree; refusing an ambiguous value.", 0.4
        )
    _, _, value, source = selected[0]
    return NumericAnswer(
        answer=value,
        page=source.pdf_page,
        confidence=0.9 if source.extraction_method == "native" else 0.7,
        source=source,
        reason="Matched entity, measure, year and column constraints. Confidence is a heuristic, not a calibrated probability.",
    )
