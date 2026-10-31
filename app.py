"""Streamlit interface for Report Navigator; launch with streamlit run app.py."""

from pathlib import Path

import streamlit as st

from ui.session import sync_document
from ui.views import footer, header, hero, steps, workspace

st.set_page_config(
    page_title="Report Navigator · Sloths", page_icon="📄", layout="wide"
)
st.html(Path(__file__).parent / "ui" / "styles.css")
header()
if "rn_navigator" not in st.session_state:
    hero()
uploaded = st.file_uploader(
    "Upload a report", type=["pdf"], key="rn_upload", max_upload_size=50
)
mode = st.radio(
    "Choose how to run",
    options=["offline", "hosted"],
    format_func=lambda choice: (
        "Offline report QA" if choice == "offline" else "Hosted Gemma demo"
    ),
    key="rn_mode",
    index=0,
)
if mode == "offline":
    st.caption("Offline mode processes the report without a cloud model.")
else:
    st.info(
        "Internet required. Your question and retrieved report evidence are sent to Google. This demo mode is separate from offline scoring."
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
if "rn_navigator" in st.session_state:
    workspace(st.session_state["rn_navigator"])
else:
    if st.session_state.get("rn_error"):
        st.error(st.session_state["rn_error"])
    steps()
footer()
