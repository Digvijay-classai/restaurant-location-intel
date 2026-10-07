"""Shared Streamlit UI pieces: CSS, footer, repo-markdown rendering, state.

Kept out of the page files so every page looks and behaves the same.
"""
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from . import theme

ROOT = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/Digvijay-classai/restaurant-location-intel"
LIVE_URL = "https://restaurant-location-intel.streamlit.app"

# Analysis inputs that must survive switching between pages. Streamlit
# deletes a widget's state when its page isn't rendered; re-assigning the
# value on every run (in app.py) keeps it.
PERSISTENT_KEYS = ("city", "cuisine", "budget", "size_sqm", "min_confidence")
WEIGHT_KEY_PREFIX = "w_"


def keep_state() -> None:
    for k in list(st.session_state.keys()):
        if k in PERSISTENT_KEYS or str(k).startswith(WEIGHT_KEY_PREFIX):
            st.session_state[k] = st.session_state[k]


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .block-container {{ padding-top: 3.75rem; padding-bottom: 2rem; max-width: 1200px; }}
        .anchor {{
            background: {theme.SURFACE}; border: 1px solid {theme.BORDER};
            border-radius: 8px; padding: 16px 20px; margin: 4px 0 12px 0;
        }}
        .anchor .label {{ color: {theme.TEXT_MUTED}; font-size: 14px; margin: 0; }}
        .anchor .hood {{ color: {theme.TEXT}; font-size: 28px; font-weight: 600; margin: 2px 0; }}
        .anchor .facts {{ color: {theme.TEXT}; font-size: 16px; margin: 0; }}
        .muted {{ color: {theme.TEXT_MUTED}; font-size: 14px; }}
        .pill {{
            background: {theme.RISK_BG}; color: {theme.RISK_TEXT}; padding: 3px 8px;
            border-radius: 10px; font-size: 12px; margin-right: 4px; display: inline-block;
        }}
        .lede {{ color: {theme.TEXT}; font-size: 20px; line-height: 1.5; max-width: 760px; margin: 4px 0 18px 0; }}
        .step {{ display: flex; gap: 14px; margin: 0 0 14px 0; max-width: 760px; }}
        .step .n {{
            flex: 0 0 30px; height: 30px; border-radius: 50%; border: 1.5px solid {theme.ACCENT};
            color: {theme.ACCENT}; font-weight: 700; text-align: center; line-height: 27px;
        }}
        .step .t {{ color: {theme.TEXT}; font-size: 16px; line-height: 1.5; }}
        .step .t b {{ display: block; }}
        dl.read {{ max-width: 820px; margin: 0; }}
        dl.read dt {{ color: {theme.TEXT}; font-weight: 600; margin-top: 12px; }}
        dl.read dd {{ color: {theme.TEXT_MUTED}; margin: 2px 0 0 0; font-size: 15px; line-height: 1.5; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def footer(uses_places: bool = False) -> None:
    st.divider()
    st.caption(
        "**Data:** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL) · "
        "Elaboración propia con datos extraídos del sitio web del [INE](https://www.ine.es) (CC BY 4.0) · "
        "Crime: Ministerio del Interior, Balance de Criminalidad 2025 (municipal; neighbourhood variation estimated) · "
        "Rent: author estimates calibrated to Cushman & Wakefield / CBRE Spain 2024 public ranges · "
        "Map tiles © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors"
        + (" · Competitor counts: Google Places (Powered by Google)" if uses_places else "")
        + f". Sources and licences: [DATA_LICENSES.md]({REPO_URL}/blob/main/DATA_LICENSES.md)."
    )
    st.caption(
        "**Disclaimer:** an independent portfolio and research project. All figures are model "
        "estimates for illustration, not financial, investment, real-estate or legal advice, and "
        "come with no warranty. Verify everything independently before any decision. Not affiliated "
        "with or endorsed by any data provider named above. "
        f"[Full disclaimer]({REPO_URL}/blob/main/DISCLAIMER.md) · "
        "**Privacy:** this app has no accounts and stores none of your inputs · "
        f"[Source code]({REPO_URL})"
    )


_REL_LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)]+)\)")


def render_repo_markdown(rel_path: str) -> None:
    """Render a markdown file from the repo, rewriting relative links to GitHub."""
    path = ROOT / rel_path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        st.info(f"{rel_path} not found. See it on [GitHub]({REPO_URL}/blob/main/{rel_path}).")
        return
    base = str(Path(rel_path).parent).replace(".", "") or ""
    def fix(m: re.Match) -> str:
        target = m.group(1)
        joined = (Path(base) / target).as_posix() if base else target
        # normalise "../" segments
        parts: list[str] = []
        for seg in joined.split("/"):
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg not in ("", "."):
                parts.append(seg)
        return f"]({REPO_URL}/blob/main/{'/'.join(parts)})"
    st.markdown(_REL_LINK.sub(fix, text))
