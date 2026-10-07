"""Folium map rendering for scored, ranked H3 hexes.

- Fill colour = composite score on a colour-blind-safe viridis ramp.
- Zones below break-even are drawn faint with a dashed outline;
  "Outskirts" (no neighbourhood data) are grey.
- Numbered pins mark the shortlist using the SAME `rank` column as the
  Rankings table and Shortlist briefs.
"""
from __future__ import annotations

import html
import math

import folium
import h3
import pandas as pd

from ..formatting import eur, months, num, pct
from ..scoring.financial_model import SHORTLIST_TIERS, TIER_OUTSKIRTS
from . import theme

MAP_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &middot; '
    'Elaboraci&oacute;n propia con datos del <a href="https://www.ine.es">INE</a>'
)


def _style(row: pd.Series) -> dict:
    tier = int(row.get("rank_tier", 0))
    if tier == TIER_OUTSKIRTS:
        return {"fill_color": theme.GREY_FILL, "fill_opacity": 0.25, "dash_array": "4 4"}
    if tier not in SHORTLIST_TIERS:  # over budget or below break-even
        return {"fill_color": theme.score_color(row["composite"]), "fill_opacity": 0.25,
                "dash_array": "4 4"}
    return {"fill_color": theme.score_color(row["composite"]), "fill_opacity": 0.75,
            "dash_array": None}


def render_score_map(
    df: pd.DataFrame,
    center: tuple[float, float],
    zoom: int = 12,
    cuisine: str = "",
    label_top: int = 10,
) -> folium.Map:
    """Return a Folium map with hexes shaded by composite and the shortlist pinned."""
    m = folium.Map(location=list(center), zoom_start=zoom, tiles=None, control_scale=True)
    # Standard OpenStreetMap tiles: no key, attribution required, light use
    # only (OSMF Tile Usage Policy, see DATA_LICENSES.md). Darkened in the
    # browser with a CSS filter to match the app theme; the filter applies to
    # the tile layer only, never to the scored hexes.
    folium.TileLayer(
        tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr=MAP_ATTRIBUTION,
        name="OpenStreetMap",
        max_zoom=19,
        className="rli-dark-tiles",
    ).add_to(m)
    m.get_root().header.add_child(folium.Element(
        "<style>.rli-dark-tiles{filter:invert(1) hue-rotate(180deg) "
        "brightness(0.85) contrast(0.9) saturate(0.6);}</style>"
    ))

    for _, row in df.iterrows():
        style = _style(row)
        hood = html.escape(str(row.get("neighbourhood", "")))
        tooltip = f"<b>{hood}</b><br>Rank {int(row['rank'])} &middot; Score {row['composite']:.1f}"
        folium.Polygon(
            locations=h3.cell_to_boundary(row["h3_id"]),
            color="#222",
            weight=0.6,
            dash_array=style["dash_array"],
            fill=True,
            fill_color=style["fill_color"],
            fill_opacity=style["fill_opacity"],
            popup=folium.Popup(_popup_html(row, cuisine), max_width=360),
            tooltip=folium.Tooltip(tooltip, sticky=True),
        ).add_to(m)

    m.get_root().html.add_child(folium.Element(_legend_html()))

    shortlist = df[df["rank_tier"].isin(SHORTLIST_TIERS)].nsmallest(label_top, "rank")
    for _, row in shortlist.iterrows():
        rank = int(row["rank"])
        folium.Marker(
            location=[row["center_lat"], row["center_lon"]],
            icon=folium.DivIcon(
                html=(
                    f"<div style='background:#111;color:#fff;border:1.5px solid #fde725;"
                    f"border-radius:50%;width:26px;height:26px;text-align:center;"
                    f"font:600 12px/23px sans-serif;box-shadow:0 2px 6px rgba(0,0,0,.5)'>"
                    f"{rank}</div>"
                ),
                icon_size=(26, 26),
                icon_anchor=(13, 13),
            ),
            tooltip=f"#{rank} &middot; {html.escape(str(row.get('neighbourhood', '')))}",
        ).add_to(m)
    return m


def _legend_html() -> str:
    stops = "".join(
        f"<span style='background:{c};width:22px;height:12px;display:inline-block'></span>"
        for c in theme.SCORE_RAMP
    )
    ticks = "".join(f"<span>{t}</span>" for t in theme.SCORE_TICKS)
    return f"""
    <div style='position: fixed; bottom: 24px; right: 18px; z-index: 999;
                background: rgba(14,17,23,0.92); color:{theme.TEXT};
                padding: 10px 14px; border-radius: 8px; font: 12px sans-serif;
                border: 1px solid {theme.BORDER}'>
      <div style='font-weight:600;margin-bottom:6px'>Composite score</div>
      <div style='display:flex;gap:0'>{stops}</div>
      <div style='display:flex;justify-content:space-between;width:110px;margin-top:2px;
                  font-size:11px;color:{theme.TEXT_MUTED}'>{ticks}</div>
      <div style='margin-top:6px;font-size:11px;color:{theme.TEXT_MUTED}'>
        Faint, dashed = below break-even or over budget<br>Grey = outside named neighbourhoods</div>
    </div>"""


def _popup_html(row: pd.Series, cuisine: str) -> str:
    def p(x) -> str:
        return f"{float(x) * 100:0.0f}"
    hood = html.escape(str(row.get("neighbourhood", "")))
    rev = row.get("monthly_revenue_eur")
    econ = ""
    if rev is not None and not (isinstance(rev, float) and math.isnan(rev)):
        cont = row["monthly_contribution_eur"]
        margin = cont / rev if rev else 0.0
        econ = (
            f"<hr style='margin:4px 0'>"
            f"<b>Unit economics ({int(row.get('size_sqm', 150))} sqm)</b><br>"
            f"Revenue: {eur(rev)}/month<br>"
            f"Rent: {eur(row['monthly_rent_eur'])}/month<br>"
            f"Store EBITDA: {eur(cont)}/month ({pct(margin, 1)})<br>"
            f"Payback: {months(row['payback_months'])}<br>"
            f"Break-even: {num(row['breakeven_covers_per_month'])} covers/month"
        )
    return (
        f"<div style='font-family: sans-serif; font-size: 12px; min-width:260px'>"
        f"<b style='font-size:14px'>#{int(row['rank'])} {hood}</b><br>"
        f"<i>{html.escape(cuisine.title()) if cuisine else 'Restaurant'}</i> &middot; "
        f"<b>Score {row['composite']:.1f}/100</b><br>"
        f"<hr style='margin:4px 0'>"
        f"Competition gap: {p(row['competition_gap'])} &middot; "
        f"Foot traffic: {p(row['foot_traffic'])}<br>"
        f"Income match: {p(row['income_match'])} &middot; "
        f"Tourism: {p(row['tourism_intensity'])}<br>"
        f"Ecosystem: {p(row['restaurant_ecosystem'])} &middot; "
        f"Spend cap.: {p(row['spend_capacity'])}<br>"
        f"Rent fit: {p(row['rent_affordability'])} &middot; "
        f"Safety: {p(row.get('safety', 0.6))}<br>"
        f"Confidence: {p(row['confidence'])}<br>"
        f"<hr style='margin:4px 0'>"
        f"Same-cuisine: {int(row['same_cuisine'])} &middot; "
        f"Total restaurants: {int(row['restaurant'])}<br>"
        f"Est. rent: {eur(row['est_rent_eur_sqm'])}/sqm &middot; "
        f"Crime: {row.get('crime_per_1000', 0):0.0f}/1k"
        f"{econ}"
        f"</div>"
    )
