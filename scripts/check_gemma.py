"""Explicit live diagnostics; synthetic evidence only, no credential output."""

import json
import re
import sys
import time
from pathlib import Path

# Support `python scripts/check_gemma.py` from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report_navigator.answering import (  # noqa: E402
    GemmaGenerator,
    assemble_evidence,
    validate_model_answer,
)
from src.report_navigator.config import Settings  # noqa: E402
from src.report_navigator.schemas import BackendError, Chunk  # noqa: E402


def run_check(settings: Settings, generator=None) -> dict:
    """Stop at the first failed stage; never serialize provider exceptions."""
    started = time.monotonic()
    deadline = started + settings.request_deadline_seconds
    generator = generator if generator is not None else GemmaGenerator(settings)
    evidence = assemble_evidence(
        (
            Chunk(
                chunk_id="smoke:p1:c1",
                document_id="smoke",
                pdf_page=1,
                text="The sample programme covered 125 districts in 2025.",
            ),
        )
    )
    question = "How many districts did the sample programme cover in 2025?"
    grounded = json.dumps(
        {
            "question": question,
            "evidence": [{"evidence_id": "E1", "text": evidence[0].text}],
        }
    )
    report = {"model": settings.model, "status": "failed", "stages": []}
    for profile in ("minimal", "system", "thinking", "grounded"):
        stage_start = time.monotonic()
        stage = {"stage": profile}
        try:
            remaining = deadline - stage_start
            if remaining <= 0:
                raise BackendError("model_timeout", "Diagnostic deadline reached.")
            raw = generator.generate(
                "Reply with OK." if profile == "minimal" else grounded,
                profile=profile,
                timeout_seconds=min(remaining, settings.timeout_seconds),
            )
            if time.monotonic() >= deadline:
                raise BackendError("model_timeout", "Diagnostic deadline reached.")
            if not raw or not raw.strip():
                raise BackendError("empty_model_response", "No text returned.")
            if profile == "grounded":
                result = validate_model_answer(raw, evidence, "smoke")
                if result.status != "answered" or not re.search(
                    r"\b125\b", result.answer
                ):
                    raise ValueError("Synthetic answer incorrect")
                stage["answer"] = result.model_dump(mode="json")
            stage["status"] = "passed"
        except BackendError as exc:
            stage.update(status="failed", code=exc.code, http_status=exc.http_status)
        except ValueError:
            stage.update(status="failed", code="invalid_model_response")
        except Exception:
            stage.update(status="failed", code="unexpected_error")
        stage["duration_seconds"] = round(time.monotonic() - stage_start, 3)
        report["stages"].append(stage)
        if stage["status"] == "failed":
            break
    else:
        report["status"] = "passed"
    report["duration_seconds"] = round(time.monotonic() - started, 3)
    return report


def main() -> int:
    try:
        report = run_check(Settings.from_env())
    except BackendError as exc:
        report = {"status": "failed", "code": exc.code}
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
