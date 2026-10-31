"""Exact output contract and organizer metric arithmetic."""

import json

import pytest
from backend import BackendError
from pydantic import ValidationError
from src.report_navigator.evaluation import evaluate
from src.report_navigator.schemas import SubmissionRecord
from src.report_navigator.submission import read_questions, write_records


@pytest.mark.parametrize(
    "changes",
    [
        {"answer": "1,200"},
        {"answer": "1200 people"},
        {"answer": "12.0"},
        {"answer": "NOT_FOUND", "page": 1},
        {"page": None},
        {"page": True},
        {"confidence": float("nan")},
        {"confidence": 1.1},
        {"answer": 1200},
    ],
)
def test_invalid_output_is_rejected(changes):
    payload = {"id": "Q1", "answer": "1200", "page": 1, "confidence": 0.8}
    payload.update(changes)
    with pytest.raises(ValidationError):
        SubmissionRecord(**payload)


def test_gold_fields_do_not_enter_questions(tmp_path):
    file = tmp_path / "questions.jsonl"
    file.write_text(
        json.dumps(
            {
                "id": "Q1",
                "question": "Count?",
                "answer": "9999",
                "gold_pages": [200],
                "qtype": "private",
            }
        )
        + "\n"
    )
    assert read_questions(file) == [("Q1", "Count?")]


def test_duplicate_ids_are_rejected(tmp_path):
    file = tmp_path / "questions.jsonl"
    file.write_text('{"id":"Q1","question":"Count?"}\n' * 2)
    with pytest.raises(BackendError):
        read_questions(file)


def test_atomic_export_and_page_range(tmp_path):
    rows = [
        SubmissionRecord(id="Q1", answer="123", page=2, confidence=0.8),
        SubmissionRecord(id="Q2", answer="NOT_FOUND", page=None, confidence=0.6),
    ]
    file = tmp_path / "answers.jsonl"
    write_records(file, rows, ["Q1", "Q2"], 2)
    payload = [json.loads(line) for line in file.read_text().splitlines()]
    assert list(payload[0]) == ["id", "answer", "page", "confidence"]
    assert payload[1]["page"] is None
    with pytest.raises(BackendError):
        write_records(file, rows, ["Q1", "Q2"], 1)


def test_official_metric_includes_unanswerable_citation_credit():
    gold = [
        {"id": "Q1", "answer": "123", "gold_pages": [2]},
        {"id": "Q2", "answer": "NOT_FOUND", "gold_pages": []},
    ]
    pred = [
        {"id": "Q1", "answer": "123", "page": 1, "confidence": 0.9},
        {"id": "Q2", "answer": "NOT_FOUND", "page": None, "confidence": 0.7},
    ]
    result = evaluate(gold, pred)
    assert result["exact_match"] == 1
    assert result["citation_accuracy"] == 0.5
    assert result["score"] == 0.875
    assert result["hallucination_rate"] == 0
