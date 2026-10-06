"""Colour tokens shared by app.py CSS and the Folium map.

Matches .streamlit/config.toml (dark base). All text tokens meet WCAG AA
(>= 4.5:1) on BG and SURFACE.
"""
from __future__ import annotations

BG = "#0e1117"
SURFACE = "#161b22"
BORDER = "#30363d"
TEXT = "#e6edf3"
TEXT_MUTED = "#a9b4bf"      # 8.9:1 on BG
ACCENT = "#5ec962"
WARN_BG = "#3d2e00"
WARN_TEXT = "#ffd27a"
RISK_BG = "#3a1f1f"
RISK_TEXT = "#ffb4a1"       # 9.6:1 on RISK_BG
GREY_FILL = "#6e7681"

# Viridis 5-stop sequential ramp: perceptually uniform and readable with
# the common colour-vision deficiencies (unlike red -> green).
SCORE_RAMP = ("#440154", "#3b528b", "#21918c", "#5ec962", "#fde725")
SCORE_TICKS = (0, 25, 50, 75, 100)


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def score_color(score: float) -> str:
    """Interpolate SCORE_RAMP for a 0-100 score."""
    s = max(0.0, min(100.0, float(score))) / 100.0
    pos = s * (len(SCORE_RAMP) - 1)
    i = min(int(pos), len(SCORE_RAMP) - 2)
    t = pos - i
    a, b = _hex_to_rgb(SCORE_RAMP[i]), _hex_to_rgb(SCORE_RAMP[i + 1])
    r, g, bl = (round(a[k] + (b[k] - a[k]) * t) for k in range(3))
    return f"#{r:02x}{g:02x}{bl:02x}"
