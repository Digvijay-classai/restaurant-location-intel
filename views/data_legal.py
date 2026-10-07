"""Data & legal page: data sources, licences, attribution and disclaimer."""
from __future__ import annotations

import streamlit as st

from src.viz.ui import footer, render_repo_markdown


tab_data, tab_disclaimer = st.tabs(["Data sources & licences", "Disclaimer & privacy"])
with tab_data:
    render_repo_markdown("DATA_LICENSES.md")
with tab_disclaimer:
    render_repo_markdown("DISCLAIMER.md")
footer()
