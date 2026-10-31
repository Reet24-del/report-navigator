# Backend integration — V3

## Public interface

```python
from backend import BackendError, load_report

navigator = load_report(pdf_bytes, uploaded_filename)
info = navigator.report_info
answer = navigator.ask(question)  # rich, UI-compatible AnswerResult
prediction = navigator.predict(question)  # exact count / NOT_FOUND + source
image = navigator.render_page(physical_pdf_page)  # PNG bytes
```

The implementation lives in src/report_navigator. The backend package preserves
the original public import. `load_report` also accepts keyword-only `settings=`
and `generator=` for configuration/tests. Do not inject a generator into scoring.

`ask()` defaults to the offline numeric solver. It returns the existing fields:
document_id, status, answer, citations and warnings. Status is answered or
insufficient_evidence. Citations contain evidence_id, pdf_page, page_label,
source_type and quote. A table source's quote is the serialized extracted row
with its headers, not an assertion that it is verbatim prose from the PDF. Label
it "Table evidence" in the interface. Use model_dump(mode="json") for dictionaries.

`predict()` returns answer, page, confidence, source and reason. answer is digits
or NOT_FOUND, source is the underlying Chunk with optional TableRow/cell metadata,
and confidence is a heuristic, not a calibrated probability. Do not display it
as a guaranteed chance of correctness. Source cell rectangles are available for
future highlighting, but no highlighting renderer is included in V2.

## Session ownership

Store one navigator per uploaded document in st.session_state. When a different
PDF is selected, clear the old navigator, answers and selected page before loading
it. Clear the same state when the upload is removed. The document SHA-256 identifies
content, not the filename. Avoid a process-global navigator shared across users.

Use Streamlit spinners for synchronous ingestion and answering. Display
searchable_pages/page_count and report_info.warnings. OCR has a per-page timeout;
some pages may remain unprocessed. No per-page UI progress callback is implemented.
Do not interpret unprocessed pages as proof that the report lacks an answer.

## Minimal frontend connection example

```python
import hashlib
import streamlit as st
from backend import BackendError, load_report

uploaded = st.file_uploader("Upload report", type=["pdf"])
if uploaded is not None:
    content = uploaded.getvalue()
    document_id = hashlib.sha256(content).hexdigest()
    if st.session_state.get("document_id") != document_id:
        for key in ("navigator", "document_id", "answer", "selected_page"):
            st.session_state.pop(key, None)
        try:
            with st.spinner("Extracting report and tables..."):
                st.session_state.navigator = load_report(content, uploaded.name)
            st.session_state.document_id = document_id
        except BackendError as error:
            st.error(error.message)
else:
    for key in ("navigator", "document_id", "answer", "selected_page"):
        st.session_state.pop(key, None)
```

Only enable Ask when a navigator exists. Clear the previous answer before making
a new request; catch BackendError and display .message. For answered results,
select a citation's pdf_page and pass it to render_page. For insufficient_evidence,
show the message without indexing an empty citations list. Do not enable unsafe
HTML for report text or model output.

## Configuration

Python 3.11 is the scoring target. Install requirements-dev.txt for tests, or
requirements.txt for application dependencies. Direct application packages are
pinned. Transitive dependency resolution is not fully locked.

The offline default does not need an API key. The declared Tesseract English model
must be available at models/tessdata/eng.traineddata. TESSDATA_PREFIX can override
the location for local UI use. Local document caches default to an OS temporary
folder and are keyed by the document, extraction settings, model hash and parser
version. No challenge data is committed. The scoring entry point disables report
cache reuse and rebuilds its index from the actual --pdf.

The optional cloud adapter was tested live in V3 with synthetic evidence. Its
configured grounded request passed; a bare request returned HTTP 500. It cannot
be used in scoring. ANSWER_MODE=hosted is an explicit local
development choice. Never set it in predict.py, which forces offline settings.
use_page_images=True raises unsupported_feature; local Gemma vision is not V2.

## Error handling

BackendError has .code and .message. Examples include invalid_pdf, encrypted_pdf,
pdf_too_large, page_limit, no_searchable_text, invalid_question, question_too_long,
unsupported_feature, invalid_page and page_render_failed. OCR errors are recorded
as page-level warnings where other report content remains usable. A report with
no usable content raises no_searchable_text.

Missing credentials/provider errors belong only to the explicit hosted mode.
They are not converted into report-absence claims. The scorer accepts only input
IDs and questions even if a local development file also contains gold fields.

## Team handoff

Team Sloths: the frontend teammate owns app.py, the backend owner owns this
package, and the validation teammate checks actual figures/pages independently.
The GitHub repository's initial README commit exists; do not assume the backend
has been published until its files are visible there. Teammate names are pending.

## V3: optional hosted Gemma diagnostics

Use the existing `navigator.ask(question)` contract. Explicit demo setup is
`load_report(pdf_bytes, filename, settings=Settings.from_env().model_copy(update={"answer_mode": "hosted"}))`.
Show this choice as "Hosted Gemma demo — internet required" in Streamlit. Scoring
continues through `predict.py`; hosted API use is prohibited there. No local
Gemma inference or image-assisted answer path was added in V3.

Run `python scripts/check_gemma.py` from the project directory after installing
requirements and setting GEMINI_API_KEY in the ignored local .env. The check
makes up to four live requests, stops on the first failure and uses synthetic
text only. It tests a minimal request, system instructions, thinking settings,
and a grounded answer with a verified quote and physical page. It prints the
model, stage, elapsed time and safe HTTP status on errors. It never prints the
key, headers or raw provider exceptions. Run it explicitly, not on Streamlit
reruns, startup or as part of ordinary tests.

Catch BackendError and display `error.message`. The optional `error.http_status`
is safe numeric diagnostic information. An API failure is not NOT_FOUND and
must not be shown as a successful offline or Gemma answer. For 400/404, inspect
request/model support; for 401/403, check project/key access; for 429, inspect
quota rather than repeatedly retrying. For transient server/network failures,
the answer path retries with exponential backoff and jitter within its shared
attempt budget. SDK retries are disabled. Default budget: two generation calls
including repair, 30 seconds per call, 45 seconds overall. Max attempts: three.
A transport timeout is clipped to the remaining deadline; scheduling and client
cleanup can add slight overhead, so this is not an operating-system hard kill.
Custom injected generators must enforce their own blocking timeout.

The API key belongs only in the local backend .env, never frontend source or
GitHub. Keep ANSWER_MODE=offline in the shared defaults. Hosted models are
explicitly restricted to gemma-4-26b-a4b-it or gemma-4-31b-it; no automatic model
substitution occurs. A hosted demo does not establish offline Gemma prize eligibility.
