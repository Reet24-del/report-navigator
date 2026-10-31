"""Question constraints, derived from text rather than organizer qtype labels."""

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"two[ -]?wheelers?", "two wheeler", text)
    text = re.sub(r"over[ -]?speeding", "overspeeding", text)
    text = re.sub(r"pedestrians?", "pedestrian", text)
    text = re.sub(r"\bnh\b", "national highways", text)
    text = re.sub(r"\bsh\b", "state highways", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


@dataclass(frozen=True)
class Query:
    question: str
    measure: str | None
    year: str | None
    entity: str
    category: str | None
    scope: str | None
    topic: str | None = None
    supported: bool = True


def parse_question(question: str) -> Query:
    text = normalize(question)
    measure = None
    if re.search(r"\b(killed|deaths?|fatalities|fatality)\b", text):
        measure = "killed"
    elif re.search(r"\binjur(?:ed|ies|y)\b", text):
        measure = "injured"
    elif re.search(r"\baccidents?\b", text):
        measure = "accidents"
    years = re.findall(r"\b(?:19|20)\d{2}\b", text)
    # V2 handles one exact count, not multi-year arithmetic or rates.
    supported = len(set(years)) <= 1 and not re.search(
        r"\b(percentage|percent|ratio|average|difference|increase|decrease)\b", text
    )
    scope = "city" if re.search(r"\b(city|cities|million plus)\b", text) else None
    category = None
    for pattern, name in [
        (r"two wheeler", "two wheeler"),
        (r"pedestrian", "pedestrian"),
        (r"overspeeding", "overspeeding"),
        (r"mobile phone", "mobile phone"),
        (r"cars?.*taxis?.*vans?", "cars taxis vans lmvs"),
    ]:
        if re.search(pattern, text):
            category = name
            break
    # Retain the entity between grammatical anchors, including parenthetical names.
    quoted = re.search(r"['\"]([^'\"]+)['\"]", question)
    if quoted:
        entity = normalize(quoted.group(1))
        if scope is None:
            scope = "national"
    elif category and re.search(
        r"\b(?:in india|in the country|national|all india)\b", text
    ):
        entity = category
        scope = "national"
    else:
        entity_text = re.sub(
            r"\b(?:in|during|for)\s+(?:the year\s+)?(?:19|20)\d{2}\b", "", text
        )
        matches = list(
            re.finditer(
                r"\bin\s+(.+?)(?=\s+(?:in|during|for|were|was|attributed)\b|$)",
                entity_text,
            )
        )
        entity = matches[-1].group(1) if matches else ""
        entity = re.sub(
            r"\b(?:city|cities|million plus|during|the year)\b", " ", entity
        )
        entity = " ".join(entity.split())
        if entity in {"india", "the country"}:
            scope = "national"
            entity = "all india"
    topic = (
        "collision"
        if "collision" in text
        else "violation"
        if "attributed" in text or category in {"mobile phone", "overspeeding"}
        else "road_user"
        if "road user" in text
        else None
    )
    return Query(
        question,
        measure,
        years[-1] if years else None,
        entity,
        category,
        scope,
        topic,
        bool(supported),
    )
