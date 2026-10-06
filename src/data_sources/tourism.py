"""Tourism intensity signals.

Tourism matters a lot for restaurant placement, especially for ethnic
cuisines (Indian, Japanese, Thai) which tourists actively seek out.

INE's Encuesta de Ocupacion Hotelera (hotel occupancy survey) publishes
monthly hotel bed counts by municipality. We keep a static table of 2024
averages in `src/cities.py` (vintage: TOURISM_VINTAGE) and combine that
top-down signal with a bottom-up OSM count of hotels and tourist POIs per
hex.
"""
from __future__ import annotations

from ..cities import CITIES, TOURISM_VINTAGE  # noqa: F401  (re-exported)

DEFAULT_TOURISM = {"hotel_beds_per_1000": 10.0, "overnight_stays_per_capita": 2.0}


def municipality_tourism(city: str) -> dict[str, float]:
    c = CITIES.get(city.lower())
    if c is None:
        return dict(DEFAULT_TOURISM)
    return {
        "hotel_beds_per_1000": c.hotel_beds_per_1000,
        "overnight_stays_per_capita": c.overnight_stays_per_capita,
    }
