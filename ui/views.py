"""Native Streamlit controls; only our static design markup uses HTML."""

from base64 import b64encode
from pathlib import Path

import streamlit as st

from backend import BackendError
from ui.session import ask_question

DOCUMENT_ICON = "data:image/svg+xml;base64," + b64encode(
    Path(__file__).with_name("document.svg").read_bytes()
).decode("ascii")


def header():
    # Streamlit strips inline SVG; a static image keeps its HTML sanitizer intact.
    st.html(
        '<header class="rn-header"><span class="rn-brand">'
        f'<img class="rn-brand-icon" src="{DOCUMENT_ICON}" alt="">'
        'Report Navigator</span><span class="rn-team">Sloths</span></header>'
    )


def hero():
    st.html(
        '<section class="rn-hero"><h1>Find the figure.<br>Keep the '
        "<span>source.</span></h1><p>Ask questions of long reports. "
        "Get answers you can trace to the page.</p></section>"
    )


def steps():
    st.html("""<section class="rn-steps">
    <div class="rn-step"><div class="rn-step-number">01</div><h3>Upload your PDF</h3><p>Add a government report or another long document. PDFs up to 50 MB.</p></div>
    <div class="rn-step"><div class="rn-step-number">02</div><h3>Ask a precise question</h3><p>For offline answers, name one count, an entity and a year.</p></div>
    <div class="rn-step"><div class="rn-step-number">03</div><h3>Check the source page</h3><p>Open the cited page and inspect the evidence behind the answer.</p></div>
    </section>""")


def footer():
    st.html('<footer class="rn-footer">Report Navigator · Sloths</footer>')


def workspace(navigator):
    info = navigator.report_info
    st.subheader("Your report")
    st.text(info.filename)
    st.caption(
        f"{info.searchable_pages} of {info.page_count} pages searchable · {info.ocr_pages} OCR pages"
    )
    for warning in info.warnings:
        st.warning(warning)
    answer_column, source_column = st.columns([1, 1.1], gap="large")
    with answer_column:
        st.subheader("Ask the report")
        with st.form("rn_ask_form"):
            question = st.text_area(
                "Your question",
                key="rn_question",
                placeholder="How many people were killed in North District in 2027?",
                height=100,
                max_chars=2000,
            )
            submitted = st.form_submit_button("Find answer", type="primary")
        if submitted:
            with st.spinner("Finding supporting evidence…"):
                ask_question(st.session_state, question)
        if st.session_state.get("rn_error"):
            st.error(st.session_state["rn_error"])
        result = st.session_state.get("rn_result")
        if result is not None:
            st.subheader("Answer")
            if result.status == "insufficient_evidence":
                st.info(result.answer)
            else:
                st.text(result.answer)
                for i, citation in enumerate(result.citations):
                    with st.container(border=True):
                        printed = (
                            f" · Printed label {citation.page_label}"
                            if citation.page_label
                            else ""
                        )
                        st.caption(
                            f"{citation.evidence_id} · PDF page {citation.pdf_page}{printed}"
                        )
                        st.caption("Table evidence / source excerpt")
                        if citation.quote:
                            st.text(citation.quote)
                        if st.button(
                            f"View PDF page {citation.pdf_page}", key=f"rn_citation_{i}"
                        ):
                            st.session_state["rn_page"] = citation.pdf_page
            for warning in result.warnings:
                if warning not in info.warnings:
                    st.warning(warning)
        else:
            st.caption(
                "An answer and its source will appear here after you ask a question."
            )
    with source_column:
        st.subheader("Source page")
        physical = int(
            st.number_input(
                "Physical PDF page",
                min_value=1,
                max_value=info.page_count,
                key="rn_page",
                step=1,
            )
        )
        st.caption("Page numbers count from the first page of the PDF.")
        try:
            st.image(navigator.render_page(physical), width="stretch")
        except BackendError as error:
            st.error(error.message)
        except Exception:
            st.error("This page could not be displayed. Try another page.")
