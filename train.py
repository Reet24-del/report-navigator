"""Reproduce deterministic pipeline configuration; no report index is shipped."""

import argparse
import hashlib
import json
from pathlib import Path

from src.report_navigator.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.data_dir.is_dir():
        parser.error("--data-dir must identify the provided public-data directory")
    settings = Settings()
    model = settings.tessdata_dir / "eng.traineddata"
    if not model.is_file():
        parser.error("Install the declared Tesseract language asset before building")
    configuration = {
        "version": 2,
        "method": "deterministic_table_retrieval",
        "chunk_words": settings.chunk_words,
        "overlap_words": settings.overlap_words,
        "candidate_count": settings.candidate_count,
        "ocr_dpi": settings.ocr_dpi,
        "ocr_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "confidence": "uncalibrated evidence-strength heuristic",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "pipeline.json").write_text(json.dumps(configuration, indent=2) + "\n")
    print(
        "Reproduced configuration. No challenge text, tables, entities or answers were saved."
    )


if __name__ == "__main__":
    main()
