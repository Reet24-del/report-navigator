"""Diagnostics use mocks in ordinary tests; never contact Google."""

import json

from scripts.check_gemma import run_check
from src.report_navigator.config import Settings
from src.report_navigator.schemas import BackendError


class FakeGenerator:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return json.dumps(
            {
                "status": "answered",
                "answer": "125 districts [E1]",
                "citations": [{"evidence_id": "E1", "quote": "covered 125 districts"}],
            }
        )


def test_stages_and_validated_answer():
    fake = FakeGenerator()
    result = run_check(Settings(), fake)
    assert result["status"] == "passed"
    assert [c["profile"] for c in fake.calls] == [
        "minimal",
        "system",
        "thinking",
        "grounded",
    ]
    assert result["stages"][-1]["answer"]["citations"][0]["pdf_page"] == 1
    assert all(0 < c["timeout_seconds"] <= 30 for c in fake.calls)


def test_safe_status_and_stop_at_first_failure():
    fake = FakeGenerator(
        BackendError("model_service_unavailable", "PRIVATE", http_status=503)
    )
    result = run_check(Settings(api_key="SECRET"), fake)
    assert len(fake.calls) == 1
    assert result["stages"][0]["http_status"] == 503
    assert "PRIVATE" not in json.dumps(result)
    assert "SECRET" not in json.dumps(result)


def test_unexpected_exception_is_not_serialized():
    result = run_check(Settings(), FakeGenerator(RuntimeError("PRIVATE")))
    assert result["stages"][0]["code"] == "unexpected_error"
    assert "PRIVATE" not in json.dumps(result)


def test_no_requests_after_deadline(monkeypatch):
    ticks = iter([0, 46, 46, 46])
    monkeypatch.setattr("scripts.check_gemma.time.monotonic", lambda: next(ticks))
    fake = FakeGenerator()
    result = run_check(Settings(), fake)
    assert not fake.calls
    assert result["stages"][0]["code"] == "model_timeout"


def test_invented_quote_fails_grounded_check():
    class InventedGenerator(FakeGenerator):
        def generate(self, prompt, **kwargs):
            return (
                super()
                .generate(prompt, **kwargs)
                .replace("covered 125 districts", "covered 999 districts")
            )

    result = run_check(Settings(), InventedGenerator())
    assert result["status"] == "failed"
    assert result["stages"][-1]["code"] == "invalid_model_response"


def test_wrong_number_does_not_pass_as_substring():
    class WrongNumberGenerator(FakeGenerator):
        def generate(self, prompt, **kwargs):
            raw = json.loads(super().generate(prompt, **kwargs))
            raw["answer"] = "1125 districts [E1]"
            return json.dumps(raw)

    result = run_check(Settings(), WrongNumberGenerator())
    assert result["status"] == "failed"
    assert result["stages"][-1]["code"] == "invalid_model_response"
