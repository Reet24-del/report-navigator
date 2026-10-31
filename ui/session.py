"""Own each user's document and request lifecycle without shared global caches."""

import hashlib

from backend import BackendError, Settings, load_report

DOCUMENT_KEYS = (
    "rn_navigator",
    "rn_result",
    "rn_error",
    "rn_page",
    "rn_question",
    "rn_last_question",
)


def clear_document(state):
    for key in list(state):
        if key.startswith("rn_question_"):
            state.pop(key, None)
    for key in DOCUMENT_KEYS:
        state.pop(key, None)
    # Explicitly reset the widget value; deleting its key alone lets Streamlit
    # restore the previous browser value when the same widget is rendered again.
    state["rn_question"] = ""


def sync_document(
    state, content, filename, mode, *, retry=False, settings=None, loader=None
):
    """One load attempt per content/mode identity; failed loads need explicit retry."""
    identity = (
        (hashlib.sha256(content).hexdigest(), mode, "v5-general-qa-1")
        if content is not None
        else None
    )
    if state.get("rn_identity") != identity:
        clear_document(state)
        state["rn_identity"] = identity
        state.pop("rn_attempted", None)
    if identity is None or (state.get("rn_attempted") == identity and not retry):
        return
    clear_document(state)
    state["rn_attempted"] = identity
    try:
        if mode not in {"offline", "hosted"}:
            raise BackendError("configuration_error", "Choose a supported answer mode.")
        configured = (settings or Settings.from_env()).model_copy(
            update={"answer_mode": mode}
        )
        state["rn_navigator"] = (loader or load_report)(
            content, filename, settings=configured
        )
        state["rn_page"] = 1
    except BackendError as error:
        state["rn_error"] = error.message
    except Exception:
        state["rn_error"] = (
            "This report could not be opened. Please retry or choose another PDF."
        )


def ask_question(state, question):
    state.pop("rn_result", None)
    state.pop("rn_error", None)
    state["rn_page"] = 1
    state["rn_last_question"] = question.strip()
    if not question.strip():
        state["rn_error"] = "Enter a question about the uploaded document."
        return
    navigator = state.get("rn_navigator")
    if navigator is None:
        state["rn_error"] = "Upload a report before asking a question."
        return
    try:
        result = navigator.ask(question.strip())
        state["rn_result"] = result
        if result.citations:
            state["rn_page"] = result.citations[0].pdf_page
    except BackendError as error:
        state["rn_error"] = error.message
    except Exception:
        state["rn_error"] = (
            "An unexpected error interrupted this request. No answer was accepted."
        )
