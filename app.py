"""Streamlit entry point: page setup and navigation.

Pages (views/):
  Home         what the tool is, how to use it, how to read results
  Analyse      the location-scoring tool
  Methodology  docs/methodology.md
  Data & legal DATA_LICENSES.md + DISCLAIMER.md
"""
from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

# Load .env BEFORE importing anything that reads env vars.
load_dotenv()

from src.viz.ui import inject_css, keep_state  # noqa: E402

st.set_page_config(
    page_title="Restaurant Location Intelligence",
    page_icon=":material/restaurant:",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
keep_state()  # analysis inputs survive moving between pages

home = st.Page("views/home.py", title="Home", icon=":material/home:", default=True)
analyze = st.Page("views/analyze.py", title="Analyse", icon=":material/insights:", url_path="analyse")
method = st.Page("views/methodology.py", title="Methodology", icon=":material/functions:",
                 url_path="methodology")
legal = st.Page("views/data_legal.py", title="Data & legal", icon=":material/gavel:",
                url_path="data-and-legal")

page = st.navigation([home, analyze, method, legal], position="top")

# A clear way back Home (and into the tool) from every other page, at the top
# of the sidebar. Kept here so page scripts stay self-contained.
if page.title != "Home":
    st.sidebar.page_link(home, label="Home", icon=":material/home:")
    if page.title != "Analyse":
        st.sidebar.page_link(analyze, label="Open the tool", icon=":material/insights:")

page.run()
