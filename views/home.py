"""Home page: what the tool is, how to use it, how to read the results."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.cities import CITIES, CITY_KEYS
from src.formatting import num
from src.pipeline import precomputed_path
from src.viz.ui import REPO_URL, ROOT, footer

SCENARIOS = [
    # (label, city, cuisine, budget)
    ("Barcelona · Italian · Medium budget", "barcelona", "italian", "medium"),
    ("Madrid · Burger · Medium budget", "madrid", "burger", "medium"),
    ("Valladolid · Burger · Low budget (a 'no' answer)", "valladolid", "burger", "low"),
]


@st.cache_data(show_spinner=False)
def coverage() -> dict:
    """Headline numbers computed from the shipped data (never hard-coded)."""
    zones = pois = tracts = residents = 0
    for city in CITY_KEYS:
        try:
            payload = json.loads(precomputed_path(city).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        zones += len(payload.get("hexes", []))
        pois += int(payload.get("meta", {}).get("n_pois", 0))
        ine = ROOT / "data" / "ine" / f"{city}.csv"
        if ine.exists():
            df = pd.read_csv(ine, usecols=["population"])
            tracts += len(df)
            residents += int(df["population"].sum())
    return {"zones": zones, "pois": pois, "tracts": tracts, "residents": residents}


def start(city: str | None = None, cuisine: str | None = None, budget: str | None = None) -> None:
    if city:
        st.session_state["city"] = city
        st.session_state["cuisine"] = cuisine
        st.session_state["budget"] = budget
    st.switch_page("views/analyze.py")


# ---- hero ---------------------------------------------------------------------

st.title("Restaurant Location Intelligence")
st.markdown(
    "<p class='lede'>Where in Barcelona, Madrid or Valladolid should a new restaurant open? "
    "This tool scores every ~0.74 km² zone of the city for your cuisine, budget and premises "
    "size, estimates the unit economics, and ranks zones by how fast they would pay back, "
    "with the source of every number shown.</p>",
    unsafe_allow_html=True,
)
if st.button("Start analysing", type="primary", icon=":material/arrow_forward:"):
    start()

c = coverage()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Cities", len(CITIES))
m2.metric("Zones scored", num(c["zones"]))
m3.metric("OpenStreetMap places", num(c["pois"]))
m4.metric("Census tracts (INE 2023)", num(c["tracts"]))

map_shot = ROOT / "docs" / "screenshots" / "map.png"
if map_shot.exists():
    st.image(str(map_shot), width=980,
             caption="The Map view: scored zones and the top-10 shortlist for one scenario.")

# ---- try an example -------------------------------------------------------------

st.subheader("Try an example")
st.caption("Opens the tool with these inputs filled in. You can change anything afterwards. "
           "The last one shows the tool saying no: no zone pays back within 10 years.")
cols = st.columns(len(SCENARIOS))
for col, (label, city, cuisine, budget) in zip(cols, SCENARIOS):
    if col.button(label, width="stretch", key=f"scenario_{city}_{cuisine}"):
        start(city, cuisine, budget)

# ---- how to use -------------------------------------------------------------------

st.subheader("How to use it")
steps = [
    ("Pick your scenario", "In the sidebar on the Analyse page, choose a city, a cuisine, a budget "
     "tier (the most rent per m² you would pay) and the premises size."),
    ("Read the top zone", "The card under the title shows the best zone: its payback period, the "
     "downside and upside cases, monthly contribution and how confident the data is."),
    ("Compare the shortlist", "<i>Shortlist</i> gives a short deal brief for the top five zones. "
     "<i>Map</i> shows every zone coloured by score, with the shortlist numbered. <i>Rankings</i> "
     "breaks each zone into its eight component scores."),
    ("Stress-test and export", "Change the premises size or, under <i>Advanced</i>, the scoring "
     "weights, and everything recomputes instantly. <i>Data</i> downloads the full table as CSV "
     "or GeoJSON."),
]
for i, (title, text) in enumerate(steps, start=1):
    st.markdown(f"<div class='step'><div class='n'>{i}</div><div class='t'><b>{title}</b>{text}</div></div>",
                unsafe_allow_html=True)

# ---- how to read results ------------------------------------------------------------

st.subheader("How to read the results")
st.markdown(
    """
<dl class="read">
<dt>Rank and status</dt>
<dd>Zones are ranked on economics first. <b>Viable</b> zones pay back their fit-out within 10 years and come first, fastest payback on top.
Then come <b>feasible, slow payback</b> zones, then <b>below break-even</b> ones. Areas outside the named neighbourhoods come last.
The same rank number appears on the map pin, in the table and in the brief.</dd>
<dt>Payback, downside and upside</dt>
<dd>Payback = fit-out cost ÷ monthly contribution. The downside case adds 20% to rent, cuts the ticket by 10% and demand by 30%; the upside case does the reverse.
A zone that only works in the base case needs a hard rent negotiation.</dd>
<dt>Composite score (0-100)</dt>
<dd>A weighted mix of eight signals: competition, foot traffic, income match, tourism, dining ecosystem, spend capacity, rent fit and safety.
It colours the map and breaks ties. It does not override the economics.</dd>
<dt>Confidence</dt>
<dd>How much data sits behind a zone: how many mapped places it has, and whether its demographics come from census tracts.
Use the sidebar filter to hide thinly mapped zones.</dd>
<dt>The coloured banner</dt>
<dd><b>Green</b> means live OpenStreetMap data plus census demographics, so briefs include a verdict.
<b>Blue</b> means the demographics are estimated, so no verdict is given. <b>Amber</b> means synthetic demo data.
The tool withholds go/no-go verdicts unless the underlying data is real.</dd>
<dt>Risk flags</dt>
<dd>Red tags on a brief, such as licensing or heritage zones, saturated competition, prime rent or demand above seat capacity, mark what to verify on site.</dd>
</dl>
""",
    unsafe_allow_html=True,
)

# ---- what it is not ---------------------------------------------------------------------

st.subheader("What it is, and what it isn't")
st.markdown(
    f"""
- **It is** a reproducible first pass: open data, a transparent model and every assumption documented on the
  **Methodology** page. Use it to shortlist neighbourhoods to walk.
- **It isn't** advice. Foot traffic is estimated from mapped places, rent figures are calibrated estimates, and the
  demand model has not yet been backtested against real openings and closures. Treat paybacks in very
  dense areas as optimistic.
- **Built by** Digvijay Singh as an independent portfolio project. Code and data are on [GitHub]({REPO_URL});
  licences and attributions are on the **Data & legal** page.
"""
)

footer()
