"""Composite scoring engine.

Each hex gets normalized component scores in [0, 1], weighted and scaled
to a final 0-100 composite. All component functions are pure (same
inputs -> same outputs, no I/O) and preserve the caller's index.

Model notes:

1. **Edge effects.** `competition_gap`, `foot_traffic`,
   `restaurant_ecosystem` and `tourism_intensity` are computed on the hex
   plus its H3 1-ring. At the edge of the study area, missing neighbours
   are imputed with the mean of the neighbours that are present, so
   boundary hexes are not artificially "uncompetitive".
2. **Daypart awareness.** Foot traffic is split into DAY (offices +
   shops + transit) and NIGHT (nightlife + hotels + tourism) and blended
   per cuisine.
3. **Spend capacity** = resident income x non-tourism activity, kept
   orthogonal to `tourism_intensity`.
4. **No constant offsets.** City-level signals (hotel beds per 1,000) are
   identical for every hex in a city, so they are not added to per-hex
   scores; they would only compress the composite range.
5. **Confidence score** per hex in [0, 1] based on data density and
   whether demographics are measured (INE tracts) or estimated.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import h3
import numpy as np
import pandas as pd

from ..cuisines import day_share, income_target
from .weights import BUDGET_MAX_RENT, COMPONENTS, normalise_weights, weights_for

POI_COLUMNS = ("restaurant", "shop", "transit", "bus_stop",
               "tourism", "hotel", "office", "nightlife", "same_cuisine")
DEMOGRAPHIC_COLUMNS = ("income_household", "income_per_capita",
                       "pct_foreign", "population_density")
FALLBACK_INCOME = 35_000.0


@dataclass
class ScoreInputs:
    cuisine: str
    budget: str                  # "low" | "medium" | "high"
    hotel_beds_per_1000: float   # municipality-level (used by the financial model)
    overnight_stays_per_capita: float
    weights: Mapping[str, float] | None = None  # None -> cuisine profile


# ---- input validation -------------------------------------------------------


def prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy that is safe to score.

    - h3_id, center_lat, center_lon are required (ValueError otherwise).
    - Missing POI columns are added as 0; NaN POI counts become 0.
    - NaN demographics are imputed from the frame median (or a national
      fallback) and the row's demographics_source becomes "imputed".
    """
    missing = [c for c in ("h3_id", "center_lat", "center_lon") if c not in df.columns]
    if missing:
        raise ValueError(f"Hex frame is missing required columns {missing}.")
    out = df.copy()
    for col in POI_COLUMNS:
        if col not in out.columns:
            out[col] = 0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).clip(lower=0)
    if "demographics_source" not in out.columns:
        out["demographics_source"] = "unknown"
    for col in DEMOGRAPHIC_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
        na = out[col].isna()
        if na.any():
            med = out[col].median()
            fallback = FALLBACK_INCOME if col == "income_household" else 0.0
            out.loc[na, col] = med if pd.notna(med) else fallback
            out.loc[na, "demographics_source"] = "imputed"
    return out


# ---- neighbourhood smoothing ------------------------------------------------


def _neighbours(hid: str, k: int) -> list[str]:
    if not isinstance(hid, str) or not h3.is_valid_cell(hid):
        return []
    return [n for n in h3.grid_disk(hid, k) if n != hid]


def ring_sum(df: pd.DataFrame, col: str, k: int = 1, w: float = 0.5) -> pd.Series:
    """value + w * (sum of neighbour values) over the hex's k-ring.

    Neighbours outside the frame (edge of the study area) are imputed with
    the mean of the neighbours that are present. Ids that are not valid
    H3 cells (arbitrary points, unit-test ids) get no neighbour term.
    Returns a Series aligned to `df.index`.
    """
    values = dict(zip(df["h3_id"], df[col].astype(float)))
    out = []
    for hid, val in zip(df["h3_id"], df[col].astype(float)):
        ring = _neighbours(hid, k)
        present = [values[n] for n in ring if n in values]
        neighbour_sum = (sum(present) / len(present)) * len(ring) if present else 0.0
        out.append(val + w * neighbour_sum)
    return pd.Series(out, index=df.index, dtype=float)


# ---- component scorers ------------------------------------------------------


def _min_max(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    lo, hi = s.min(), s.max()
    if s.empty or not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def _competition_gap(df: pd.DataFrame) -> pd.Series:
    """exp(-0.5 * same-cuisine competitors over hex + 1-ring)."""
    return np.exp(-0.5 * df["same_cuisine_ring"].clip(lower=0))


def _daypart_blend(df: pd.DataFrame, cuisine: str) -> pd.Series:
    """Weighted traffic by cuisine daypart (lunch vs dinner)."""
    day_w = day_share(cuisine)
    day = (
        0.45 * df["office"]
        + 0.35 * df["shop"]
        + 0.20 * (df["transit"] + 0.4 * df["bus_stop"])
    )
    night = 0.55 * df["nightlife"] + 0.25 * df["hotel"] + 0.20 * df["tourism"]
    raw = day_w * day + (1 - day_w) * night
    smoothed = ring_sum(pd.DataFrame({"h3_id": df["h3_id"], "_t": raw}, index=df.index), "_t", w=0.4)
    return _min_max(smoothed)


def _income_match(income_household: pd.Series, target: float) -> pd.Series:
    """Gaussian around the cuisine's ideal income (sigma = EUR 10k)."""
    sigma = 10_000.0
    return np.exp(-((income_household - target) ** 2) / (2 * sigma * sigma))


def _tourism_intensity(df: pd.DataFrame) -> pd.Series:
    """Local hotel + tourist POIs over hex + 1-ring, min-max within the city."""
    raw = df["hotel"] * 1.5 + df["tourism"]
    smoothed = ring_sum(pd.DataFrame({"h3_id": df["h3_id"], "_t": raw}, index=df.index), "_t", w=0.6)
    return _min_max(smoothed)


def _restaurant_ecosystem(df: pd.DataFrame) -> pd.Series:
    """Bell curve on total restaurant density over hex + 1-ring.

    Peaks at ~14 (healthy dining district incl. neighbours); zero
    restaurants is a red flag (0.1), 30+ is saturated.
    """
    x = ring_sum(df, "restaurant", w=0.5)
    peak, width = 14.0, 10.0
    base = np.exp(-((x - peak) ** 2) / (2 * width * width))
    return base.where(x > 0, 0.1)


def _spend_capacity(df: pd.DataFrame) -> pd.Series:
    """Resident purchasing power x non-tourism activity (transit, offices, shops)."""
    income_norm = ((df["income_household"] - 20_000) / 25_000).clip(0, 1)
    activity = _min_max(df["transit"] + 0.6 * df["office"] + 0.4 * df["shop"])
    return (0.6 * income_norm + 0.4 * activity).clip(0, 1)


def _rent_affordability(est_rent: pd.Series, budget: str) -> pd.Series:
    """Logistic of estimated rent against the user's budget ceiling."""
    cap = BUDGET_MAX_RENT.get(budget, BUDGET_MAX_RENT["medium"])
    ratio = est_rent / cap
    return (1.0 / (1.0 + np.exp(4.0 * (ratio - 1.0)))).clip(0, 1)


def _safety(df: pd.DataFrame) -> pd.Series:
    """safety = exp(-crime/120): 0 -> 1.0, 60 -> 0.61, 120 -> 0.37, 240 -> 0.14."""
    if "crime_per_1000" not in df.columns:
        return pd.Series(0.6, index=df.index)
    crime = pd.to_numeric(df["crime_per_1000"], errors="coerce").fillna(120.0)
    return np.exp(-crime / 120.0).clip(0, 1)


def _confidence(df: pd.DataFrame) -> pd.Series:
    """Per-hex confidence [0, 1] from data density and demographic source.

    60% POI density (log-scaled, saturates at 100 POIs) + 40% demographics:
    measured INE tract data = 1.0, estimated/imputed = 0.5.
    """
    poi_total = sum(df[c] for c in POI_COLUMNS if c != "same_cuisine")
    poi_score = (np.log1p(poi_total) / np.log1p(100)).clip(0, 1)
    demo_score = (df["demographics_source"] == "ine_csv").astype(float)
    return (0.6 * poi_score + 0.4 * (0.5 + 0.5 * demo_score)).clip(0, 1)


# ---- rent estimator ---------------------------------------------------------


def estimate_rent_eur_per_sqm(
    income_household: pd.Series,
    foot_traffic_raw: pd.Series,
    listing_rents: pd.Series | None = None,
    listing_n: pd.Series | None = None,
    shrink_k: float = 15.0,
) -> pd.Series:
    """Ground-floor commercial rent (EUR / sqm / month) per hex, in [10, 220].

    If `listing_rents` (per-neighbourhood rent from data/rent/) is provided,
    we Bayesian-shrink toward the modelled proxy using listing-count weight:
        blended = (n * listed + k * modelled) / (n + k)
    with k=15. A neighbourhood with 60 listings leans ~80% on the listings;
    one with 4 listings leans ~21% on them.

    Proxy = two-factor model on income (purchasing power) and POI
    density (frontage demand), calibrated against Cushman & Wakefield
    and CBRE Spain high-street benchmarks (2024).
    """
    income_factor = (income_household - 20_000) / 25_000
    traffic_factor = _min_max(foot_traffic_raw)
    modelled = 22.0 + 55.0 * income_factor.clip(0, 1.5) + 48.0 * traffic_factor
    modelled = modelled.clip(lower=10.0, upper=220.0)
    if listing_rents is None:
        return modelled

    listed = pd.to_numeric(listing_rents, errors="coerce").fillna(modelled)
    if listing_n is None:
        n = pd.Series(10.0, index=listed.index)
    else:
        n = pd.to_numeric(listing_n, errors="coerce").fillna(0).astype(float)
    weight = n / (n + shrink_k)
    blended = weight * listed + (1 - weight) * modelled
    return blended.clip(lower=10.0, upper=220.0)


# ---- public API -------------------------------------------------------------


def score_hexes(df: pd.DataFrame, inputs: ScoreInputs) -> pd.DataFrame:
    """Score every hex row and return a copy with component + composite columns.

    Expected input columns: h3_id, center_lat, center_lon; POI counts
    (restaurant, shop, transit, bus_stop, tourism, hotel, office,
    nightlife, same_cuisine); demographics (income_household, ...).
    Missing POI columns are treated as 0. The caller's index is preserved.
    """
    out = prepare_frame(df)
    if out.empty:
        for col in (*COMPONENTS, "same_cuisine_ring", "est_rent_eur_sqm", "confidence", "composite"):
            out[col] = pd.Series(dtype=float)
        return out

    foot_raw = (
        out["shop"] + out["transit"] + 0.4 * out["bus_stop"]
        + out["office"] + out["nightlife"]
    )
    out["est_rent_eur_sqm"] = estimate_rent_eur_per_sqm(
        out["income_household"], foot_raw,
        listing_rents=out["listing_rent"] if "listing_rent" in out.columns else None,
        listing_n=out["listing_n"] if "listing_n" in out.columns else None,
    )

    out["same_cuisine_ring"]    = ring_sum(out, "same_cuisine", w=0.5)
    out["competition_gap"]      = _competition_gap(out)
    out["foot_traffic"]         = _daypart_blend(out, inputs.cuisine)
    out["income_match"]         = _income_match(out["income_household"], income_target(inputs.cuisine))
    out["tourism_intensity"]    = _tourism_intensity(out)
    out["restaurant_ecosystem"] = _restaurant_ecosystem(out)
    out["spend_capacity"]       = _spend_capacity(out)
    out["rent_affordability"]   = _rent_affordability(out["est_rent_eur_sqm"], inputs.budget)
    out["safety"]               = _safety(out)
    out["confidence"]           = _confidence(out)

    weights = (normalise_weights(inputs.weights) if inputs.weights is not None
               else weights_for(inputs.cuisine))
    composite = sum(out[c] * weights[c] for c in COMPONENTS)
    out["composite"] = (composite * 100).round(1)
    return out
