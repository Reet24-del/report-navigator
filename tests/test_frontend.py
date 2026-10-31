"""Session lifecycle and native Streamlit behavior, without cloud requests."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from backend import AnswerResult, BackendError, Citation, Settings
from ui.session import ask_question, sync_document


def fake_navigator():
    answer = AnswerResult(
        document_id="doc",
        status="answered",
        answer="73 [E1]",
        citations=(
            Citation(evidence_id="E1", pdf_page=2, quote="73 people were killed."),
        ),
    )
    return SimpleNamespace(ask=Mock(return_value=answer))


def test_reruns_do_not_reload_and_mode_change_clears_answer():
    state = {}
    loader = Mock(side_effect=[fake_navigator(), fake_navigator()])
    for _ in range(3):
        sync_document(
            state, b"pdf", "a.pdf", "offline", settings=Settings(), loader=loader
        )
    assert loader.call_count == 1
    ask_question(state, "How many were killed?")
    assert state["rn_page"] == 2
    sync_document(state, b"pdf", "a.pdf", "hosted", settings=Settings(), loader=loader)
    assert loader.call_count == 2
    assert "rn_result" not in state
    assert state["rn_page"] == 1
    assert loader.call_args.kwargs["settings"].answer_mode == "hosted"


def test_removal_and_replacement_clear_previous_report():
    state = {}
    loader = Mock(
        side_effect=[fake_navigator(), BackendError("invalid_pdf", "Invalid PDF.")]
    )
    sync_document(state, b"a", "a.pdf", "offline", settings=Settings(), loader=loader)
    ask_question(state, "How many?")
    sync_document(state, b"b", "b.pdf", "offline", settings=Settings(), loader=loader)
    assert "rn_navigator" not in state and "rn_result" not in state
    assert state["rn_error"] == "Invalid PDF."
    sync_document(state, None, "", "offline", settings=Settings(), loader=loader)
    assert "rn_error" not in state and "rn_navigator" not in state


def test_failed_ingestion_waits_for_explicit_retry():
    state = {}
    loader = Mock(side_effect=[RuntimeError("PRIVATE"), fake_navigator()])
    sync_document(state, b"a", "a.pdf", "offline", settings=Settings(), loader=loader)
    sync_document(state, b"a", "a.pdf", "offline", settings=Settings(), loader=loader)
    assert loader.call_count == 1
    assert "PRIVATE" not in state["rn_error"]
    sync_document(
        state, b"a", "a.pdf", "offline", settings=Settings(), loader=loader, retry=True
    )
    assert loader.call_count == 2 and "rn_navigator" in state


@pytest.mark.parametrize(
    "code", ["missing_api_key", "model_service_unavailable", "rate_limit"]
)
def test_provider_failures_clear_previous_answers_without_fallback(code):
    nav = fake_navigator()
    state = {"rn_navigator": nav, "rn_result": "old"}
    nav.ask.side_effect = BackendError(code, "Safe provider error.")
    ask_question(state, "How many?")
    assert "rn_result" not in state
    assert state["rn_error"] == "Safe provider error."
    assert nav.ask.call_count == 1


def test_blank_question_does_not_call_backend():
    nav = fake_navigator()
    state = {"rn_navigator": nav}
    ask_question(state, "  ")
    nav.ask.assert_not_called()
    assert state["rn_error"]


def test_native_landing_and_hosted_disclosure():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(
        timeout=20
    )
    assert not app.exception
    assert app.radio[0].value == "offline"
    app.radio[0].set_value("hosted").run()
    assert not app.exception
    assert any("sent to Google" in item.value for item in app.info)


def test_workspace_answer_persists_on_page_rerun(monkeypatch):
    import pymupdf

    import ui.session

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((30, 30), "Source evidence")
        png = page.get_pixmap().tobytes("png")
    nav = fake_navigator()
    nav.report_info = SimpleNamespace(
        filename="synthetic.pdf",
        searchable_pages=2,
        page_count=2,
        ocr_pages=0,
        warnings=(),
    )
    nav.render_page = Mock(return_value=png)

    def inject(state, *args, **kwargs):
        state["rn_navigator"] = nav
        if "rn_page" not in state:
            state["rn_page"] = 1

    monkeypatch.setattr(ui.session, "sync_document", inject)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(
        timeout=20
    )
    assert not app.exception
    app.text_area[0].set_value("How many people were killed?")
    app.button(key="FormSubmitter:rn_ask_form-Find answer").click().run()
    assert not app.exception
    assert nav.ask.call_count == 1
    assert app.number_input[0].value == 2
    app.number_input[0].set_value(1).run()
    assert not app.exception
    assert nav.ask.call_count == 1


def test_setup_transition_does_not_reload_report_and_removal_restores_landing(
    monkeypatch,
):
    import pymupdf
    import streamlit as st

    import ui.session

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((30, 30), "Invented source")
        png = page.get_pixmap().tobytes("png")
    nav = fake_navigator()
    nav.report_info = SimpleNamespace(
        filename="synthetic.pdf",
        searchable_pages=2,
        page_count=2,
        ocr_pages=0,
        warnings=(),
    )
    nav.render_page = Mock(return_value=png)
    source = {
        "upload": SimpleNamespace(name="synthetic.pdf", getvalue=lambda: b"invented")
    }
    loader = Mock(return_value=nav)
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: source["upload"])
    monkeypatch.setattr(ui.session, "load_report", loader)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(
        timeout=20
    )
    assert not app.exception
    assert loader.call_count == 1
    assert not app.expander[0].proto.expanded
    app.run()
    assert loader.call_count == 1
    source["upload"] = None
    app.run()
    assert not app.exception
    assert app.expander[0].proto.expanded
    assert "rn_navigator" not in app.session_state
