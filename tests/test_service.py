"""Exercise the public frontend interface with real PDFs and controlled inference."""

import json

import pymupdf
import pytest
from backend import BackendError, Settings, load_report


def report_pdf(text):
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 550, 780), text, fontsize=11)
        return document.tobytes()


class FixedGenerator:
    def __init__(self, quote):
        self.quote = quote
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(
            {
                "status": "answered",
                "answer": self.quote + " [E1]",
                "citations": [{"evidence_id": "E1", "quote": self.quote}],
            }
        )


def test_public_flow_and_document_isolation(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    first_text = (
        "District Alpha recorded 125 households participating in agriculture in 2023."
    )
    second_text = (
        "District Beta recorded 900 households participating in agriculture in 2024."
    )
    first_model = FixedGenerator(first_text)
    second_model = FixedGenerator(second_text)
    first = load_report(
        report_pdf(first_text), "alpha.pdf", settings=settings, generator=first_model
    )
    second = load_report(
        report_pdf(second_text), "beta.pdf", settings=settings, generator=second_model
    )
    first_answer = first.ask("How many households in Alpha?")
    second_answer = second.ask("How many households in Beta?")
    assert "125" in first_answer.answer and "900" not in first_answer.answer
    assert "900" in second_answer.answer and "125" not in second_answer.answer
    assert first_answer.document_id != second_answer.document_id
    assert "Alpha" not in second_model.prompts[0]
    assert first.render_page(1).startswith(b"\x89PNG\r\n\x1a\n")
    assert first_answer.model_dump(mode="json")["citations"][0]["pdf_page"] == 1


@pytest.mark.parametrize("question", ["", "   ", None, 123])
def test_question_validation(question, tmp_path):
    navigator = load_report(
        report_pdf(
            "This statistical report describes district agricultural coverage in 2023."
        ),
        "report.pdf",
        settings=Settings(cache_dir=tmp_path),
    )
    with pytest.raises(BackendError) as caught:
        navigator.ask(question)
    assert caught.value.code == "invalid_question"


def test_unsupported_image_mode_is_explicit(tmp_path):
    navigator = load_report(
        report_pdf(
            "This statistical report describes district agricultural coverage in 2023."
        ),
        "report.pdf",
        settings=Settings(cache_dir=tmp_path),
    )
    assert "page_images" not in navigator.report_info.supported_features
    with pytest.raises(BackendError) as caught:
        navigator.ask("coverage?", use_page_images=True)
    assert caught.value.code == "unsupported_feature"


@pytest.mark.parametrize("page", [0, -1, 2, True, "1"])
def test_invalid_source_page(page, tmp_path):
    navigator = load_report(
        report_pdf(
            "This statistical report describes district agricultural coverage in 2023."
        ),
        "report.pdf",
        settings=Settings(cache_dir=tmp_path),
    )
    with pytest.raises(BackendError) as caught:
        navigator.render_page(page)
    assert caught.value.code == "invalid_page"


def test_cache_write_failure_keeps_document_usable(tmp_path, monkeypatch):
    def fail_write(*args):
        raise PermissionError("cache is unwritable")

    monkeypatch.setattr("src.report_navigator.service.write_cache", fail_write)
    navigator = load_report(
        report_pdf(
            "This statistical report describes district agricultural coverage in 2023."
        ),
        "report.pdf",
        settings=Settings(cache_dir=tmp_path),
    )
    assert navigator.report_info.searchable_pages == 1
    assert "cache could not be saved" in navigator.report_info.warnings[-1]


def test_question_length_limit(tmp_path):
    navigator = load_report(
        report_pdf(
            "This statistical report describes district agricultural coverage in 2023."
        ),
        "report.pdf",
        settings=Settings(cache_dir=tmp_path, max_question_chars=20),
    )
    with pytest.raises(BackendError) as caught:
        navigator.ask("coverage " * 10)
    assert caught.value.code == "question_too_long"
