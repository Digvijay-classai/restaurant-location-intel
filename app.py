"""Streamlit entry point for the Restaurant Location Intelligence Tool.

Screen hierarchy:
  1. Provenance bar   — what data this is (SYNTHETIC / LIVE, vintages)
  2. Anchor card      — the #1 zone, payback range, confidence
  3. Tabs             — Shortlist | Map | Rankings | Method | Data

Everything recomputes when an input changes (scoring a snapshot takes
well under a second), so labels and data can never disagree. One `rank`
column (economics-first, see financial_model.rank_zones) drives the map
pins, the Rankings table and the Shortlist.
"""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

# Load .env BEFORE importing anything that reads env vars.
load_dotenv()

from src.cities import CITIES, CITY_KEYS  # noqa: E402
from src.cuisines import CUISINE_KEYS  # noqa: E402
from src.data_sources.overture_maps import OverpassError  # noqa: E402
from src.export import NESTED_COLUMNS, to_geojson  # noqa: E402
from src.formatting import eur, eur_k, months, num, pct  # noqa: E402
from src.geo.boundaries import city_center  # noqa: E402
from src.pipeline import (is_synthetic, run_pipeline_with_meta,  # noqa: E402
                          verdicts_allowed)
from src.scoring.financial_model import (MAX_SIZE_SQM, MIN_SIZE_SQM,  # noqa: E402
                                         REFERENCE_SIZE_SQM, TIER_LABELS,
                                         deal_brief, rank_zones)
from src.scoring.weights import BUDGET_MAX_RENT, COMPONENTS, weights_for  # noqa: E402
from src.viz import theme  # noqa: E402
from src.viz.maps import render_score_map  # noqa: E402

ROOT = Path(__file__).resolve().parent
METHODOLOGY = ROOT / "docs" / "methodology.md"

COMPONENT_HELP = {
    "competition_gap": "Fewer same-cuisine restaurants in this hex and its 6 neighbours = higher.",
    "foot_traffic": "Pedestrian proxy from shops, offices and transit (lunch) and bars and hotels (dinner), weighted by the cuisine's lunch/dinner split.",
    "income_match": "How close local household income is to the cuisine's ideal price point.",
    "tourism_intensity": "Hotels and attractions nearby, relative to the rest of the city.",
    "restaurant_ecosystem": "Peaks for an established dining street (~14 restaurants incl. neighbours); empty or saturated areas score low.",
    "rent_affordability": "Estimated rent against your budget tier's ceiling.",
    "spend_capacity": "Resident purchasing power x everyday (non-tourist) activity.",
    "safety": "Registered crime per 1,000 residents, inverted.",
}

st.set_page_config(
    page_title="Restaurant Location Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    .block-container {{ padding-top: 3.75rem; padding-bottom: 2rem; }}  /* clears the Streamlit toolbar */
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
    </style>
    """,
    unsafe_allow_html=True,
)


# ---- sidebar ----------------------------------------------------------------

st.sidebar.title("Location Intelligence")
st.sidebar.caption("Score and rank urban zones for a new restaurant.")

city = st.sidebar.selectbox("City", CITY_KEYS, index=CITY_KEYS.index("barcelona"),
                            format_func=lambda k: CITIES[k].name)
cuisine = st.sidebar.selectbox("Cuisine", CUISINE_KEYS, index=0, format_func=str.title)
budget = st.sidebar.radio(
    "Budget tier",
    ["low", "medium", "high"],
    index=1,
    horizontal=True,
    format_func=str.title,
    help=(
        "Max rent per sqm/month: "
        f"low ≤ {eur(BUDGET_MAX_RENT['low'])}, "
        f"medium ≤ {eur(BUDGET_MAX_RENT['medium'])}, "
        f"high ≤ {eur(BUDGET_MAX_RENT['high'])}"
    ),
)
size_sqm = st.sidebar.number_input(
    "Premises size (sqm)",
    min_value=int(MIN_SIZE_SQM), max_value=int(MAX_SIZE_SQM),
    value=int(REFERENCE_SIZE_SQM), step=10,
    help="Drives seats (2.5 sqm/seat), rent, capex and fixed costs.",
)

with st.sidebar.expander("Advanced: scoring weights"):
    defaults = weights_for(cuisine)
    raw_weights = {
        c: st.slider(c.replace("_", " ").title(), 0.0, 1.0, round(defaults[c], 2), 0.01,
                     key=f"w_{cuisine}_{c}", help=COMPONENT_HELP[c])
        for c in COMPONENTS
    }
    if st.button("Reset to cuisine defaults", width="stretch"):
        for c in COMPONENTS:
            st.session_state.pop(f"w_{cuisine}_{c}", None)
        st.rerun()
    st.caption("Weights are re-normalised to sum to 100%. The ranking is economics-first; "
               "weights change the composite score, which breaks ties and colours the map.")

min_confidence = st.sidebar.slider(
    "Minimum confidence",
    0.0, 1.0, 0.20, 0.05,
    help="Hide zones with sparse data (few POIs, estimated demographics).",
)
if st.sidebar.button("Clear cache", width="stretch"):
    st.cache_data.clear()
    st.sidebar.success("Cache cleared — results recomputed.")


# ---- compute ----------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _run(city: str, cuisine: str, budget: str, weights: tuple, size_sqm: float):
    res = run_pipeline_with_meta(city, cuisine, budget, weights=dict(weights), size_sqm=size_sqm)
    return res.df, res.meta


weights_key = tuple(sorted(raw_weights.items()))
try:
    with st.spinner(f"Scoring {CITIES[city].name}…"):
        scored, meta = _run(city, cuisine, budget, weights_key, float(size_sqm))
except (ValueError, OverpassError, FileNotFoundError) as exc:
    st.error(f"Could not score {CITIES[city].name}. {exc}")
    st.stop()

# Confidence filter BEFORE ranking, so ranks are contiguous for what is shown.
df = scored[scored["confidence"] >= min_confidence]
n_hidden = len(scored) - len(df)
if df.empty:
    st.warning(
        f"All {len(scored)} zones are below the {min_confidence:.0%} confidence filter. "
        "Lower **Minimum confidence** in the sidebar."
    )
    st.stop()
df = rank_zones(df)
allow_verdicts = verdicts_allowed(meta)


# ---- 1. provenance bar --------------------------------------------------------

sources = meta.get("sources", {})
vint = meta.get("vintages", {})
SOURCE_LABELS = {
    "synthetic": "SYNTHETIC", "osm_overpass": "OpenStreetMap (live)",
    "ine_csv": "INE census tracts", "city_median": "city medians (estimated)",
    "google_places": "Google Places", "osm": "OpenStreetMap", "mixed": "mixed",
}
rent_label = {"seeded_cw_cbre_2024": "author estimates calibrated to C&W/CBRE 2024 ranges (+ model)",
              "none": "modelled proxy"}.get(meta.get("rent", "none"),
                                            meta.get("rent", "").replace("_", " ") + " (+ model)")
prov = (
    f"POIs: {SOURCE_LABELS.get(sources.get('pois'), sources.get('pois'))}"
    f"{' ' + vint['pois'] if vint.get('pois') not in (None, 'synthetic') else ''} · "
    f"Demographics: {SOURCE_LABELS.get(sources.get('demographics'), sources.get('demographics'))} · "
    f"Competitors: {SOURCE_LABELS.get(sources.get('competitors'), sources.get('competitors'))} · "
    f"Rent: {rent_label} · Crime: {vint.get('crime', '—')} · Tourism: {vint.get('tourism', '—')}"
)
if is_synthetic(meta):
    st.warning(
        f"**SYNTHETIC DEMO DATA. Not real market figures.** {CITIES[city].name} is shown on "
        "randomly generated POIs and demographics so the app runs offline. Rankings and euros "
        "illustrate the method only; no verdicts are given. Refresh with real data: "
        f"`python scripts/pull_live_data.py {city}`.\n\n{prov}"
    )
elif not allow_verdicts:
    st.info(
        "**Live POIs, estimated demographics.** Numbers are shown, but go/no-go verdicts are "
        f"withheld until INE tract data is added (`data/ine/{city}.csv`).\n\n{prov}"
    )
else:
    st.success(f"**Live data.** {prov}")


# ---- 2. anchor card -----------------------------------------------------------

st.markdown(
    f"<h2 style='margin:0'>{html.escape(CITIES[city].name)} · {html.escape(cuisine.title())} · "
    f"{budget.title()} budget · {num(size_sqm)} sqm</h2>",
    unsafe_allow_html=True,
)
shortlist = df[df["rank_tier"] <= 1].sort_values("rank")
n_viable = int((df["rank_tier"] == 0).sum())
if shortlist.empty:
    nxt = {"low": "Medium", "medium": "High"}.get(budget)
    tip = (f"Try the {nxt} budget tier, a smaller premises, or "
           if nxt else "Try a smaller premises or ")
    st.markdown(
        f"<div class='anchor'><p class='label'>No zone clears break-even</p>"
        f"<p class='facts'>None of the {len(df)} zones shown covers its fixed costs for a "
        f"{num(size_sqm)} sqm {html.escape(cuisine)} concept at this budget. {tip}"
        "lowering the confidence filter.</p></div>",
        unsafe_allow_html=True,
    )
else:
    best = shortlist.iloc[0]
    margin = best["monthly_contribution_eur"] / best["monthly_revenue_eur"] if best["monthly_revenue_eur"] else 0
    st.markdown(
        f"<div class='anchor'>"
        f"<p class='label'>#1 {TIER_LABELS[int(best['rank_tier'])]} zone</p>"
        f"<p class='hood'>{html.escape(best['neighbourhood'])}</p>"
        f"<p class='facts'>Payback {months(best['payback_months'])} "
        f"(downside {months(best['payback_low_months'])}, upside {months(best['payback_high_months'])})"
        f" · contribution {eur(best['monthly_contribution_eur'])}/month ({pct(margin, 1)} margin)"
        f" · confidence {pct(best['confidence'])} · score {best['composite']:.1f}</p>"
        f"<p class='muted'>{n_viable} of {len(df)} zones pay back within 10 years"
        f"{f' · {n_hidden} hidden by the confidence filter' if n_hidden else ''}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---- 3. tabs ------------------------------------------------------------------

tab_short, tab_map, tab_rank, tab_method, tab_data = st.tabs(
    ["Shortlist", "Map", "Rankings", "Method", "Data"]
)

with tab_short:
    st.caption(
        f"Top 5 zones that clear break-even, by rank. {num(size_sqm)} sqm casual dining, "
        f"{int(round(size_sqm / 2.5))} seats, lunch (menú del día) + dinner split per cuisine. "
        "Costs: rent, a fixed core team plus labour per cover, fixed OpEx, 30% food cost. "
        "Downside/upside cases flex rent ±20%, ticket ±10% and demand ±30%."
    )
    if shortlist.empty:
        st.info("No zone clears break-even with the current inputs. See the suggestion above.")
    for _, row in shortlist.head(5).iterrows():
        with st.container(border=True):
            left, right = st.columns([2, 1])
            with left:
                st.markdown(f"### #{int(row['rank'])} · {row['neighbourhood']}")
                st.markdown(deal_brief(row, cuisine, CITIES[city].name, verdicts_allowed=allow_verdicts))
                if row["risk_flags"]:
                    st.markdown(
                        " ".join(f"<span class='pill'>{html.escape(f)}</span>" for f in row["risk_flags"]),
                        unsafe_allow_html=True,
                    )
            with right:
                rev = row["monthly_revenue_eur"]
                margin = row["monthly_contribution_eur"] / rev if rev else 0
                st.metric("Contribution / month", eur(row["monthly_contribution_eur"]))
                st.caption(f"{pct(margin, 1)} margin · downside {eur(row['contribution_low_eur'])}"
                           f" · upside {eur(row['contribution_high_eur'])}")
                st.metric("Payback", months(row["payback_months"]))
                st.caption(f"Capex {eur_k(row['capex_eur'])}")
                st.caption(
                    f"Confidence {pct(row['confidence'])} · Crime {num(row['crime_per_1000'])}/1k · "
                    f"Rent {eur(row['est_rent_eur_sqm'])}/sqm ({row.get('rent_source', 'model')})"
                )

uses_places = sources.get("competitors") == "google_places"

with tab_map:
    if uses_places:
        # Google Maps Platform terms: Places content must not be shown with a
        # non-Google map. Rankings/Shortlist (no map) remain available.
        st.info("Map hidden: this snapshot's competitor counts come from Google Places, which "
                "Google's terms don't allow on a non-Google map. Use Shortlist and Rankings.")
    else:
        fmap = render_score_map(df, center=city_center(city), cuisine=cuisine)
        st_folium(fmap, height=560, use_container_width=True, returned_objects=[])  # streamlit-folium API
    st.caption(
        "Hexagons are H3 cells (~0.74 km²). Numbered pins = shortlist ranks (same numbers as "
        "the Shortlist and Rankings). Faint dashed hexes are below break-even; grey hexes are "
        "outside named neighbourhoods. Click a hex for its breakdown."
    )

with tab_rank:
    top = df.sort_values("rank").head(25).copy()
    top["status"] = top["rank_tier"].map(TIER_LABELS)
    top["margin"] = (top["monthly_contribution_eur"] / top["monthly_revenue_eur"]).where(
        top["monthly_revenue_eur"] > 0, 0.0)
    top["payback"] = top["payback_months"].map(months)
    cols = ["rank", "neighbourhood", "status", "payback", "monthly_contribution_eur", "margin",
            "composite", "confidence", *COMPONENTS, "same_cuisine", "restaurant",
            "monthly_revenue_eur", "est_rent_eur_sqm", "crime_per_1000"]
    st.dataframe(
        top[cols],
        width="stretch",
        hide_index=True,
        column_config={
            "rank": st.column_config.NumberColumn("Rank", help="Economics-first rank (same as map pins)."),
            "neighbourhood": "Neighbourhood",
            "status": st.column_config.TextColumn("Status", help="viable = pays back within 10 years."),
            "payback": "Payback",
            "monthly_contribution_eur": st.column_config.NumberColumn(
                "Contribution (€/month)", format="localized",
                help="Revenue minus rent, labour, food and fixed OpEx (before tax and debt)."),
            "margin": st.column_config.NumberColumn("Margin", format="percent"),
            "composite": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%.1f",
                help="Weighted composite of the 8 components (weights in the sidebar)."),
            "confidence": st.column_config.ProgressColumn(
                "Confidence", min_value=0, max_value=1, format="%.2f",
                help="Data density + whether demographics are measured."),
            **{c: st.column_config.ProgressColumn(
                c.replace("_", " ").capitalize(), min_value=0, max_value=1, format="%.2f",
                help=COMPONENT_HELP[c]) for c in COMPONENTS},
            "same_cuisine": st.column_config.NumberColumn("Same-cuisine", help="Direct competitors in the hex."),
            "restaurant": st.column_config.NumberColumn("Restaurants", help="All restaurants in the hex."),
            "monthly_revenue_eur": st.column_config.NumberColumn("Revenue (€/month)", format="localized"),
            "est_rent_eur_sqm": st.column_config.NumberColumn("Rent (€/sqm/month)", format="%.0f"),
            "crime_per_1000": st.column_config.NumberColumn("Crime / 1k", format="%.0f"),
        },
    )

with tab_method:
    try:
        st.markdown(METHODOLOGY.read_text(encoding="utf-8"))
    except OSError:
        st.info("Methodology file not found. See docs/methodology.md in the repository.")


@st.cache_data(show_spinner=False)
def _geojson_bytes(cache_key: tuple, _frame: pd.DataFrame) -> bytes:
    """Cached on `cache_key` (the inputs); `_frame` is excluded from hashing."""
    return to_geojson(_frame)


with tab_data:
    export = df.sort_values("rank").drop(columns=list(NESTED_COLUMNS), errors="ignore")
    stem = f"{city}_{cuisine}_{budget}_{int(size_sqm)}sqm"
    st.download_button(
        "Download scored dataset (CSV)",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"{stem}_scored.csv",
        mime="text/csv",
        width="stretch",
    )
    st.download_button(
        "Download scored hexes (GeoJSON)",
        data=_geojson_bytes((city, cuisine, budget, weights_key, float(size_sqm), min_confidence), export),
        file_name=f"{stem}_scored.geojson",
        mime="application/geo+json",
        width="stretch",
    )
    st.caption(f"Snapshot: {meta.get('generated_with', 'unknown')}"
               f"{' at ' + meta['generated_at'] if meta.get('generated_at') else ''}.")
    st.dataframe(export, width="stretch", height=420, hide_index=True)


# ---- footer: attribution, disclaimer, privacy --------------------------------

st.divider()
st.caption(
    "**Data:** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL) · "
    "Elaboración propia con datos extraídos del sitio web del [INE](https://www.ine.es) (CC BY 4.0) · "
    "Crime: Ministerio del Interior, Balance de Criminalidad 2025 (municipal; neighbourhood variation estimated) · "
    "Rent: author estimates calibrated to Cushman & Wakefield / CBRE Spain 2024 public ranges · "
    "Map tiles © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors"
    + (" · Competitor counts: Google Places (Powered by Google)" if uses_places else "")
    + ". Sources and licences: [DATA_LICENSES.md](https://github.com/Digvijay-classai/restaurant-location-intel/blob/main/DATA_LICENSES.md)."
)
st.caption(
    "**Disclaimer:** an independent portfolio and research project. All figures are model "
    "estimates for illustration, not financial, investment, real-estate or legal advice, and "
    "come with no warranty. Verify everything independently before any decision. Not affiliated "
    "with or endorsed by any data provider named above. "
    "[Full disclaimer](https://github.com/Digvijay-classai/restaurant-location-intel/blob/main/DISCLAIMER.md) · "
    "**Privacy:** this app has no accounts and stores none of your inputs."
)
