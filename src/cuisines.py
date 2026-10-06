"""Single registry of supported cuisines.

Adding a cuisine means adding one `Cuisine` entry below and a weight
profile in `src/scoring/weights.py` (optional — the default profile is
used otherwise).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cuisine:
    key: str
    osm_aliases: frozenset[str]   # exact OSM `cuisine=*` tokens
    places_type: str              # Google Places (New) primary type
    income_target: float          # ideal annual household income, EUR
    day_share: float              # share of covers at lunch (menu del dia)
    lunch_ticket: float           # EUR per cover
    dinner_ticket: float          # EUR per cover incl. drinks


CUISINES: dict[str, Cuisine] = {c.key: c for c in (
    Cuisine("indian", frozenset({"indian", "pakistani", "bangladeshi", "nepalese", "punjabi"}),
            "indian_restaurant", 34_000, 0.55, 12.5, 24.0),
    Cuisine("italian", frozenset({"italian", "pizza", "pasta"}),
            "italian_restaurant", 38_000, 0.55, 14.0, 28.0),
    # Japanese lunch sets run 18-22; omakase operators often skip lunch.
    Cuisine("japanese", frozenset({"japanese", "sushi", "ramen"}),
            "japanese_restaurant", 48_000, 0.42, 18.0, 42.0),
    Cuisine("mexican", frozenset({"mexican", "tex-mex", "tex_mex", "taco", "tacos"}),
            "mexican_restaurant", 30_000, 0.55, 12.0, 22.0),
    Cuisine("burger", frozenset({"burger", "american"}),
            "hamburger_restaurant", 32_000, 0.60, 11.0, 19.0),
    Cuisine("chinese", frozenset({"chinese", "cantonese", "dim_sum", "sichuan"}),
            "chinese_restaurant", 30_000, 0.58, 11.5, 20.0),
    Cuisine("mediterranean", frozenset({"mediterranean", "spanish", "tapas", "greek"}),
            "mediterranean_restaurant", 40_000, 0.52, 15.0, 30.0),
    Cuisine("thai", frozenset({"thai"}),
            "thai_restaurant", 40_000, 0.48, 14.5, 28.0),
)}

CUISINE_KEYS: list[str] = list(CUISINES)

DEFAULT_DAY_SHARE = 0.52
DEFAULT_LUNCH_TICKET = 13.5
DEFAULT_DINNER_TICKET = 24.0
DEFAULT_INCOME_TARGET = 35_000.0


def osm_cuisine_tokens(tag: str | None) -> set[str]:
    """Split an OSM `cuisine` tag ("pizza;italian") into normalised tokens."""
    if not tag:
        return set()
    return {t.strip().lower().replace(" ", "_") for t in tag.split(";") if t.strip()}


def matches(cuisine: str, tag: str | None) -> bool:
    """True if an OSM cuisine tag contains one of the cuisine's exact aliases.

    Exact token match: "latin_american" does NOT count as "american".
    """
    c = CUISINES.get(cuisine.lower())
    if c is None:
        return False
    return bool(osm_cuisine_tokens(tag) & c.osm_aliases)


def day_share(cuisine: str) -> float:
    c = CUISINES.get(cuisine.lower())
    return c.day_share if c else DEFAULT_DAY_SHARE


def income_target(cuisine: str) -> float:
    c = CUISINES.get(cuisine.lower())
    return c.income_target if c else DEFAULT_INCOME_TARGET


def tickets(cuisine: str) -> tuple[float, float]:
    """(lunch, dinner) ticket in EUR per cover."""
    c = CUISINES.get(cuisine.lower())
    if c is None:
        return DEFAULT_LUNCH_TICKET, DEFAULT_DINNER_TICKET
    return c.lunch_ticket, c.dinner_ticket
