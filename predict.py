"""Offline scoring entry point. No cloud model is imported or called here."""

import argparse
import os
import sys
import time
from pathlib import Path

for variable in (
    "OMP_NUM_THREADS",
    "OMP_THREAD_LIMIT",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
):
    os.environ[variable] = "1"

# Thread limits must be set before importing NumPy/PDF processing dependencies.
from src.report_navigator import BackendError, Settings, load_report  # noqa: E402
from src.report_navigator.schemas import NumericAnswer  # noqa: E402
from src.report_navigator.submission import read_questions, record, write_records  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline report question answering")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.monotonic()
    settings = Settings(answer_mode="offline", cache_enabled=False)
    try:
        questions = read_questions(args.questions)
        # Caches are bypassed: ingestion/indexing must use this run's input PDF.
        navigator = load_report(args.pdf.read_bytes(), args.pdf.name, settings=settings)
        records = []
        for identifier, question in questions:
            if time.monotonic() - started >= settings.runtime_seconds:
                prediction = NumericAnswer(
                    answer="NOT_FOUND",
                    confidence=0,
                    reason="Runtime budget exhausted; no evidence was evaluated for this question.",
                )
            else:
                try:
                    prediction = navigator.predict(question)
                except BackendError as error:
                    if error.code not in {"invalid_question", "question_too_long"}:
                        raise
                    prediction = NumericAnswer(
                        answer="NOT_FOUND", confidence=0, reason=error.message
                    )
            records.append(
                record(identifier, prediction, navigator.report_info.page_count)
            )
        write_records(
            args.output,
            records,
            [identifier for identifier, _ in questions],
            navigator.report_info.page_count,
        )
        print(
            f"Wrote {len(records)} records in {time.monotonic() - started:.2f}s; indexed {navigator.report_info.searchable_pages}/{navigator.report_info.page_count} pages.",
            file=sys.stderr,
        )
        return 0
    except (BackendError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
