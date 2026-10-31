"""Lexical retrieval; scores rank passages, never represent confidence."""

import re
import unicodedata
from dataclasses import dataclass

from rank_bm25 import BM25Plus

from .query import normalize, parse_question
from .schemas import BackendError, Chunk

STOP_WORDS = frozenset(
    "a an the is are was were be been being of to in on at for from and or with by what which who when where how does do did please tell me about report according this that it its".split()
)


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"\b(deaths?|fatalities|fatality)\b", "killed", normalized)
    return [
        token
        for token in re.findall(r"\w+(?:[.,]\d+)*", normalized)
        if token not in STOP_WORDS
    ]


@dataclass(frozen=True)
class SearchIndex:
    chunks: tuple[Chunk, ...]
    token_sets: tuple[frozenset[str], ...]
    bm25: BM25Plus


def build_index(chunks: tuple[Chunk, ...]) -> SearchIndex:
    documents = [tokenize(chunk.text) for chunk in chunks]
    if not documents or not any(documents):
        raise BackendError(
            "empty_index", "The extracted report has no searchable terms."
        )
    # BM25Plus avoids Okapi's zero/negative IDF surprises on very small corpora.
    return SearchIndex(
        chunks, tuple(frozenset(tokens) for tokens in documents), BM25Plus(documents)
    )


def retrieve(question: str, index: SearchIndex, k: int = 6) -> tuple[Chunk, ...]:
    if k < 1:
        raise BackendError("invalid_input", "The retrieval count must be positive.")
    tokens = tokenize(question)
    if not tokens:
        return ()
    query = set(tokens)
    scores = index.bm25.get_scores(tokens)
    # Plus has a score baseline even for unmatched documents: explicitly require overlap.
    candidates = [
        i for i, terms in enumerate(index.token_sets) if query.intersection(terms)
    ]
    ranked = sorted(
        candidates, key=lambda i: (-float(scores[i]), index.chunks[i].chunk_id)
    )
    return tuple(index.chunks[i] for i in ranked[:k])


def retrieve_candidates(
    question: str, index: SearchIndex, k: int = 40
) -> tuple[Chunk, ...]:
    """Rank table rows with entity/year constraints; retain lexical fallback evidence."""
    query = parse_question(question)
    entity_tokens = set(normalize(query.entity).split())
    tokens = tokenize(question)
    if not tokens:
        return ()
    scores = index.bm25.get_scores(tokens)
    ranked = []
    for position, chunk in enumerate(index.chunks):
        if chunk.table is None:
            continue
        label_tokens = set(normalize(chunk.table.label).split())
        if entity_tokens and not entity_tokens.issubset(label_tokens):
            continue
        context = normalize(
            chunk.table.title
            + " "
            + " ".join(cell.header for cell in chunk.table.cells)
        )
        bonus = 12 if entity_tokens and entity_tokens == label_tokens else 6
        if query.year and query.year in context:
            bonus += 3
        if query.measure and query.measure in tokenize(context):
            bonus += 3
        ranked.append((-(float(scores[position]) + bonus), chunk.chunk_id, chunk))
    ranked.sort(key=lambda item: (item[0], item[1]))
    rows = [item[2] for item in ranked[:k]]
    seen = {chunk.chunk_id for chunk in rows}
    rows.extend(
        chunk
        for chunk in retrieve(question, index, min(k, 6))
        if chunk.chunk_id not in seen
    )
    return tuple(rows[:k])
