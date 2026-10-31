"""The exact scoring schema, independent of UI explanations and gold labels."""

import json
from pathlib import Path

from .schemas import BackendError, NumericAnswer, SubmissionRecord
from .storage import _atomic_write


def read_questions(path: Path) -> list[tuple[str, str]]:
    questions = []
    identifiers = set()
    try:
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise BackendError(
                        "invalid_questions", f"Question line {number} is blank."
                    )
                item = json.loads(line)
                identifier, question = item["id"], item["question"]
                if (
                    not isinstance(identifier, str)
                    or not identifier
                    or identifier in identifiers
                ):
                    raise BackendError(
                        "invalid_questions",
                        f"Question line {number} has a missing or duplicate ID.",
                    )
                if not isinstance(question, str) or not question.strip():
                    raise BackendError(
                        "invalid_questions",
                        f"Question line {number} has no question text.",
                    )
                identifiers.add(identifier)
                # Never propagate extra fields such as answer, gold_pages or qtype.
                questions.append((identifier, question))
    except (OSError, ValueError, KeyError, TypeError):
        raise BackendError(
            "invalid_questions", "Could not read valid question JSONL records."
        ) from None
    return questions


def record(
    identifier: str, prediction: NumericAnswer, page_count: int
) -> SubmissionRecord:
    result = SubmissionRecord(
        id=identifier,
        answer=prediction.answer,
        page=prediction.page,
        confidence=prediction.confidence,
    )
    if result.page is not None and result.page > page_count:
        raise BackendError(
            "invalid_prediction", "A predicted page is outside this PDF."
        )
    return result


def write_records(
    path: Path,
    records: list[SubmissionRecord],
    expected_ids: list[str],
    page_count: int,
):
    if len(records) != len(expected_ids) or [row.id for row in records] != expected_ids:
        raise BackendError(
            "invalid_prediction",
            "The output IDs must exactly match the input IDs and order.",
        )
    if len(set(expected_ids)) != len(expected_ids):
        raise BackendError("invalid_prediction", "Output IDs must be unique.")
    if any(row.page is not None and row.page > page_count for row in records):
        raise BackendError(
            "invalid_prediction", "A predicted page is outside this PDF."
        )
    content = "".join(row.model_dump_json() + "\n" for row in records)
    _atomic_write(path, content.encode("utf-8"))
