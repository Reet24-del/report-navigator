"""Reject malformed citations; never confuse provider failure with report absence."""

import json

import httpx
import pytest
from google.genai import errors

from backend import BackendError, Chunk, Settings
from src.report_navigator.answering import (
    GemmaGenerator,
    assemble_evidence,
    generate_answer,
    validate_model_answer,
)


def source_evidence():
    return assemble_evidence(
        (
            Chunk(
                chunk_id="doc:p12:c1",
                document_id="doc",
                pdf_page=12,
                page_label="9",
                text="Coverage was 55 percent in 2023 for rural households.",
            ),
        )
    )


def model_json(**updates):
    payload = {
        "status": "answered",
        "answer": "Coverage was 55 percent in 2023. [E1]",
        "citations": [
            {"evidence_id": "E1", "quote": "Coverage was 55 percent in 2023"}
        ],
    }
    payload.update(updates)
    return json.dumps(payload)


class SequenceGenerator:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_page_references_are_assigned_by_backend():
    result = validate_model_answer(model_json(), source_evidence(), "doc")
    assert result.citations[0].pdf_page == 12
    assert result.citations[0].page_label == "9"
    assert result.document_id == "doc"


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        model_json(
            answer="Coverage was 55 percent. [E99]",
            citations=[{"evidence_id": "E99", "quote": "Coverage was 55 percent"}],
        ),
        model_json(
            citations=[{"evidence_id": "E1", "quote": "Coverage was 99 percent"}]
        ),
        model_json(citations=[]),
        model_json(answer="An answer without its inline source."),
        model_json(answer="Answer [E1] and an unknown source [E2]."),
        model_json(status="insufficient_evidence"),
        model_json(pdf_page=999),
        model_json(citations=[{"evidence_id": "E1", "quote": "   "}]),
    ],
)
def test_invalid_evidence_is_rejected(raw):
    with pytest.raises(ValueError):
        validate_model_answer(raw, source_evidence(), "doc")


def test_whitespace_normalization_does_not_change_digits():
    raw = model_json(
        citations=[{"evidence_id": "E1", "quote": "Coverage was 55\n percent in 2023"}]
    )
    assert validate_model_answer(raw, source_evidence(), "doc").status == "answered"


def test_malformed_output_gets_one_repair_attempt():
    generator = SequenceGenerator("invalid", model_json())
    result = generate_answer(
        "What was coverage?", source_evidence(), "doc", Settings(), generator
    )
    assert result.status == "answered"
    assert len(generator.prompts) == 2
    assert "failed validation" in generator.prompts[1]


def test_repair_budget_is_bounded():
    generator = SequenceGenerator("invalid", "invalid")
    with pytest.raises(BackendError) as caught:
        generate_answer("coverage?", source_evidence(), "doc", Settings(), generator)
    assert caught.value.code == "invalid_model_response"
    assert len(generator.prompts) == 2


def test_provider_error_is_not_insufficient_evidence():
    generator = SequenceGenerator(BackendError("rate_limit", "quota reached"))
    with pytest.raises(BackendError) as caught:
        generate_answer("coverage?", source_evidence(), "doc", Settings(), generator)
    assert caught.value.code == "rate_limit"
    assert len(generator.prompts) == 1


def test_transient_failure_uses_same_global_attempt_budget(monkeypatch):
    monkeypatch.setattr("src.report_navigator.answering.time.sleep", lambda _: None)
    generator = SequenceGenerator(
        BackendError("model_timeout", "timed out"), model_json()
    )
    assert (
        generate_answer(
            "coverage?", source_evidence(), "doc", Settings(), generator
        ).status
        == "answered"
    )
    assert len(generator.prompts) == 2


def test_absent_evidence_never_calls_provider():
    generator = SequenceGenerator()
    assert (
        generate_answer("volcanoes?", (), "doc", Settings(), generator).status
        == "insufficient_evidence"
    )
    assert not generator.prompts


def test_model_abstention_uses_canonical_message():
    raw = model_json(
        status="insufficient_evidence",
        answer="Untrusted model explanation",
        citations=[],
    )
    result = validate_model_answer(raw, source_evidence(), "doc")
    assert (
        result.answer
        == "I couldn't find sufficient evidence in the indexed report pages."
    )


def test_missing_key_is_clear():
    with pytest.raises(BackendError) as caught:
        GemmaGenerator(Settings()).generate("test")
    assert caught.value.code == "missing_api_key"


@pytest.mark.parametrize(
    "error, expected",
    [
        (
            errors.ClientError(429, {"error": {"message": "private provider details"}}),
            "rate_limit",
        ),
        (
            errors.ClientError(403, {"error": {"message": "private provider details"}}),
            "model_access_denied",
        ),
        (
            errors.ClientError(400, {"error": {"message": "private provider details"}}),
            "model_request_error",
        ),
        (
            errors.ServerError(503, {"error": {"message": "private provider details"}}),
            "model_service_unavailable",
        ),
        (httpx.ReadTimeout("private provider details"), "model_timeout"),
        (httpx.ConnectError("private provider details"), "model_service_unavailable"),
    ],
)
def test_real_sdk_boundary_maps_errors_and_disables_hidden_retries(
    monkeypatch, error, expected
):
    from types import SimpleNamespace

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = SimpleNamespace(generate_content=self.request)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, **kwargs):
            raise error

    monkeypatch.setattr("src.report_navigator.answering.genai.Client", FakeClient)
    with pytest.raises(BackendError) as caught:
        GemmaGenerator(Settings(api_key="test-key")).generate("test")
    assert caught.value.code == expected
    assert "private provider details" not in str(caught.value)
    assert captured["http_options"].retry_options.attempts == 1
    assert captured["http_options"].timeout == 30000


def test_status_is_available_without_provider_details(monkeypatch):
    from types import SimpleNamespace

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = SimpleNamespace(generate_content=self.request)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, **kwargs):
            raise errors.ServerError(500, {"error": {"message": "PRIVATE"}})

    monkeypatch.setattr("src.report_navigator.answering.genai.Client", FakeClient)
    with pytest.raises(BackendError) as caught:
        GemmaGenerator(Settings(api_key="SECRET")).generate("test")
    assert caught.value.http_status == 500
    assert "PRIVATE" not in str(caught.value)


def test_deadline_prevents_retry(monkeypatch):
    ticks = iter([0, 44.9, 44.9])
    monkeypatch.setattr(
        "src.report_navigator.answering.time.monotonic", lambda: next(ticks)
    )
    generator = SequenceGenerator(BackendError("model_timeout", "timed out"))
    with pytest.raises(BackendError) as caught:
        generate_answer("coverage?", source_evidence(), "doc", Settings(), generator)
    assert caught.value.code == "model_timeout"
    assert len(generator.prompts) == 1


def test_transient_then_invalid_share_three_call_budget(monkeypatch):
    monkeypatch.setattr("src.report_navigator.answering.time.sleep", lambda _: None)
    generator = SequenceGenerator(
        BackendError("model_timeout", "timed out"), "invalid", model_json()
    )
    result = generate_answer(
        "coverage?", source_evidence(), "doc", Settings(max_attempts=3), generator
    )
    assert result.status == "answered"
    assert len(generator.prompts) == 3


def test_unknown_model_rejected():
    with pytest.raises(ValueError):
        Settings(model="gemini-other")


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_provider_response_rejected(monkeypatch, text):
    from types import SimpleNamespace

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(text=text)
            )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("src.report_navigator.answering.genai.Client", FakeClient)
    with pytest.raises(BackendError) as caught:
        GemmaGenerator(Settings(api_key="SECRET")).generate("test")
    assert caught.value.code == "empty_model_response"


def test_request_timeout_is_clipped_to_overall_deadline(monkeypatch):
    captured = {}

    def fake_generate(self, prompt, **kwargs):
        captured.update(kwargs)
        return model_json()

    monkeypatch.setattr(GemmaGenerator, "generate", fake_generate)
    result = generate_answer(
        "coverage?", source_evidence(), "doc", Settings(request_deadline_seconds=2)
    )
    assert result.status == "answered"
    assert 0 < captured["timeout_seconds"] <= 2
