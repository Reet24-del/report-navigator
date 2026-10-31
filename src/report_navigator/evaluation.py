"""Local organizer-metric evaluation. This module is never imported by predict.py."""

import argparse
import json
from pathlib import Path


def _normalize_answer(answer):
    return str(answer).replace(",", "").replace(" ", "")


def evaluate(gold: list[dict], predictions: list[dict]) -> dict:
    predicted = {item["id"]: item for item in predictions}
    if len(predicted) != len(predictions) or set(predicted) != {
        item["id"] for item in gold
    }:
        raise ValueError("Prediction IDs must be unique and match gold IDs exactly.")
    rows = []
    for item in gold:
        prediction = predicted[item["id"]]
        found = prediction["answer"] != "NOT_FOUND"
        answerable = item["answer"] != "NOT_FOUND"
        exact = _normalize_answer(prediction["answer"]) == _normalize_answer(
            item["answer"]
        )
        cited = prediction["page"] in item["gold_pages"] if answerable else not found
        rows.append(
            {
                "id": item["id"],
                "qtype": item.get("qtype", "unknown"),
                "exact": exact,
                "citation_correct": cited,
                "answerable": answerable,
                "found": found,
                "confidence": prediction["confidence"],
            }
        )
    count = len(rows)
    em = sum(row["exact"] for row in rows) / count if count else 0
    citation = sum(row["citation_correct"] for row in rows) / count if count else 0
    absent = [row for row in rows if not row["answerable"]]
    answerable = [row for row in rows if row["answerable"]]
    top = sorted(rows, key=lambda row: (-row["confidence"], row["id"]))[
        : max(1, (count + 1) // 2)
    ]
    return {
        "questions": count,
        "exact_match": em,
        "citation_accuracy": citation,
        "score": 0.75 * em + 0.25 * citation,
        "hallucination_rate": sum(row["found"] for row in absent) / len(absent)
        if absent
        else 0,
        "answerable_recall": sum(row["found"] for row in answerable) / len(answerable)
        if answerable
        else 0,
        "top_half_confidence_em": sum(row["exact"] for row in top) / len(top)
        if top
        else 0,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def load(path):
        return [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]

    result = evaluate(load(args.gold), load(args.predictions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "rows"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
