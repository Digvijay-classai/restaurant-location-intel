"""Weight profiles for the composite score.

Each cuisine has a weight profile (normalised to sum to 1.0). Cuisines are
tuned from how they are actually sold:

- Ethnic cuisines (Indian, Thai, Japanese) lean on tourism and the
  competition gap; they trade a bit of foot-traffic weight.
- Mass-market cuisines (burger, pizza) lean on foot traffic and dining
  ecosystem; they are commodity enough that cannibalisation is less fatal.
- High-end cuisines (japanese, mediterranean) lean on income match and
  spend capacity.

Daypart split, income targets and tickets live in `src/cuisines.py`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..cuisines import CUISINES

COMPONENTS: tuple[str, ...] = (
    "competition_gap",
    "foot_traffic",
    "income_match",
    "tourism_intensity",
    "restaurant_ecosystem",
    "rent_affordability",
    "spend_capacity",
    "safety",
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "competition_gap":      0.18,
    "foot_traffic":         0.16,
    "income_match":         0.11,
    "tourism_intensity":    0.12,
    "restaurant_ecosystem": 0.11,
    "rent_affordability":   0.09,
    "spend_capacity":       0.15,
    "safety":               0.08,
}

SAFETY_WEIGHT = 0.08

CUISINE_PROFILES: dict[str, dict[str, float]] = {
    "indian":        {"competition_gap": 0.24, "foot_traffic": 0.15,
                      "income_match": 0.10, "tourism_intensity": 0.19,
                      "restaurant_ecosystem": 0.10, "rent_affordability": 0.08,
                      "spend_capacity": 0.14, "safety": SAFETY_WEIGHT},
    "japanese":      {"competition_gap": 0.22, "foot_traffic": 0.14,
                      "income_match": 0.16, "tourism_intensity": 0.18,
                      "restaurant_ecosystem": 0.08, "rent_affordability": 0.06,
                      "spend_capacity": 0.16, "safety": SAFETY_WEIGHT},
    "thai":          {"competition_gap": 0.25, "foot_traffic": 0.14,
                      "income_match": 0.10, "tourism_intensity": 0.21,
                      "restaurant_ecosystem": 0.08, "rent_affordability": 0.08,
                      "spend_capacity": 0.14, "safety": SAFETY_WEIGHT},
    "mexican":       {"competition_gap": 0.22, "foot_traffic": 0.20,
                      "income_match": 0.10, "tourism_intensity": 0.13,
                      "restaurant_ecosystem": 0.13, "rent_affordability": 0.10,
                      "spend_capacity": 0.12, "safety": SAFETY_WEIGHT},
    "chinese":       {"competition_gap": 0.22, "foot_traffic": 0.20,
                      "income_match": 0.10, "tourism_intensity": 0.13,
                      "restaurant_ecosystem": 0.13, "rent_affordability": 0.10,
                      "spend_capacity": 0.12, "safety": SAFETY_WEIGHT},
    "italian":       {"competition_gap": 0.19, "foot_traffic": 0.19,
                      "income_match": 0.12, "tourism_intensity": 0.10,
                      "restaurant_ecosystem": 0.17, "rent_affordability": 0.10,
                      "spend_capacity": 0.13, "safety": SAFETY_WEIGHT},
    "burger":        {"competition_gap": 0.17, "foot_traffic": 0.25,
                      "income_match": 0.10, "tourism_intensity": 0.09,
                      "restaurant_ecosystem": 0.17, "rent_affordability": 0.10,
                      "spend_capacity": 0.12, "safety": SAFETY_WEIGHT},
    "mediterranean": {"competition_gap": 0.17, "foot_traffic": 0.19,
                      "income_match": 0.13, "tourism_intensity": 0.12,
                      "restaurant_ecosystem": 0.17, "rent_affordability": 0.09,
                      "spend_capacity": 0.13, "safety": SAFETY_WEIGHT},
}

# Backwards-compatible views over the cuisine registry.
CUISINE_DAYPART: dict[str, dict[str, float]] = {
    k: {"day": c.day_share, "night": round(1 - c.day_share, 4)} for k, c in CUISINES.items()
}
CUISINE_INCOME_TARGET: dict[str, float] = {k: c.income_target for k, c in CUISINES.items()}

# Max rent per sqm/month per budget tier (EUR). Spanish ground-floor
# commercial brackets, 2024 — "high" covers secondary high-street
# (BCN Rambla Catalunya pocket, MAD Chamberi/Chueca). True prime
# (Paseo de Gracia, Serrano) runs EUR 150-240/sqm and sits above `high`.
BUDGET_MAX_RENT: dict[str, float] = {
    "low":     30.0,
    "medium":  60.0,
    "high":   120.0,
}


def normalise_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Keep only known components, clamp negatives to 0, sum to 1.0.

    All-zero input falls back to equal weights rather than dividing by 0.
    """
    w = {c: max(0.0, float(weights.get(c, 0.0))) for c in COMPONENTS}
    s = sum(w.values())
    if s <= 0:
        return {c: 1.0 / len(COMPONENTS) for c in COMPONENTS}
    return {c: v / s for c, v in w.items()}


def weights_for(cuisine: str) -> dict[str, float]:
    """Return the normalised weight profile for a cuisine (default if unknown)."""
    return normalise_weights(CUISINE_PROFILES.get(cuisine.lower(), DEFAULT_WEIGHTS))
