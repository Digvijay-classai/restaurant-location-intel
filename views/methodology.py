"""Methodology page: renders docs/methodology.md (single source of truth)."""
from __future__ import annotations


from src.viz.ui import footer, render_repo_markdown


render_repo_markdown("docs/methodology.md")
footer()
