"""Streamlit interface for Report Navigator; launch with streamlit run app.py."""

from pathlib import Path

import streamlit as st

from ui.session import sync_document
from ui.views import footer, header, hero, steps, workspace

st.set_page_config(
    page_title="Report Navigator · Sloths", page_icon="📄", layout="wide"
)
st.html(Path(__file__).parent / "ui" / "styles.css")
was_loaded = "rn_navigator" in st.session_state
header()
if not was_loaded:
    hero()
    # The initial setup is open and unframed; loaded reports expose its toggle.
    st.html("<style>.st-key-rn-report-settings summary {display:none}</style>")

with st.container(key="rn-report-settings"):
    with st.expander("Report settings", expanded=not was_loaded):
        with st.container(key="rn-setup"):
            upload_column, mode_column = st.columns([2, 1], gap="large")
            with upload_column:
                st.subheader("Upload a report")
                uploaded = st.file_uploader(
                    "PDF report",
                    type=["pdf"],
                    key="rn_upload",
                    max_upload_size=50,
                    label_visibility="collapsed",
                )
            with mode_column:
                st.subheader("Choose how to run")
                mode = st.radio(
                    "Answer mode",
                    options=["offline", "hosted"],
                    format_func=lambda choice: (
                        "Offline report QA"
                        if choice == "offline"
                        else "Hosted Gemma demo"
                    ),
                    key="rn_mode",
                    index=0,
                    label_visibility="collapsed",
                )
                if mode == "offline":
                    st.caption("Offline mode uses no cloud model.")
                else:
                    st.caption("Internet required · Google Gemma")
            if mode == "hosted":
                st.info(
                    "Your question and retrieved report evidence are sent to Google. "
                    "This demo mode is separate from offline scoring."
                )

content = uploaded.getvalue() if uploaded is not None else None
filename = uploaded.name if uploaded is not None else ""
retry = False
if (
    content is not None
    and st.session_state.get("rn_error")
    and "rn_navigator" not in st.session_state
):
    retry = st.button("Retry opening report")
with st.spinner("Reading report, tables and scanned pages…", show_time=True):
    sync_document(st.session_state, content, filename, mode, retry=retry)

is_loaded = "rn_navigator" in st.session_state
if was_loaded != is_loaded:
    # One presentation-only rerun closes setup after load and restores the hero
    # after removal/failure. sync_document retains its existing load-attempt guard.
    st.rerun()
if is_loaded:
    workspace(st.session_state["rn_navigator"])
else:
    if st.session_state.get("rn_error"):
        st.error(st.session_state["rn_error"])
    steps()
footer()
