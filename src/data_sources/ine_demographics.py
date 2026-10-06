"""INE (Instituto Nacional de Estadistica) demographics adapter.

Three signals per zone:

- Population density
- Average household income (Atlas de Distribucion de Renta de los Hogares)
- Share of foreign-born residents

Income and population are published at seccion censal (census tract)
level. `scripts/fetch_ine_tracts.py <city>` downloads them from INE into
data/ine/<city>.csv (schema in data/ine/README.md).

Join to hexes, matching the revenue model's 1 km catchment: every tract
whose centroid lies within CATCHMENT_RADIUS_KM of the hex centre
contributes; density = residents in the disc / disc area, income and
foreign share are population-weighted. If no tract centroid is that close
(large peripheral tracts), the nearest tract's own values are used. CSVs
without a `population` column fall back to the nearest tract.

If no CSV is present, demographic signals fall back to city-level medians
and the municipal population density from `src/cities.py`. Those rows carry
`source="city_median"` and the UI labels them as estimated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..cities import CITIES, INCOME_VINTAGE  # noqa: F401  (re-exported)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "ine"

# Used only when a city has neither a tract CSV nor a registry entry.
FALLBACK_INCOME = {"income_household": 35_000.0, "income_per_capita": 15_000.0, "pct_foreign": 15.0}
# Used only for cities missing from the registry; flagged as estimated.
FALLBACK_POPULATION_DENSITY = 5_000.0

REQUIRED_COLUMNS = (
    "lat", "lon", "income_household", "income_per_capita",
    "pct_foreign", "population_density",
)
CATCHMENT_RADIUS_KM = 1.0


@dataclass
class ZoneDemographics:
    income_household: float
    income_per_capita: float
    pct_foreign: float
    population_density: float  # people per km2
    source: str  # "ine_csv" or "city_median"


def city_defaults(city: str) -> ZoneDemographics:
    c = CITIES.get(city.lower())
    if c is None:
        m = FALLBACK_INCOME
        return ZoneDemographics(m["income_household"], m["income_per_capita"],
                                m["pct_foreign"], FALLBACK_POPULATION_DENSITY, "city_median")
    return ZoneDemographics(
        income_household=c.income_household,
        income_per_capita=c.income_per_capita,
        pct_foreign=c.pct_foreign,
        population_density=c.population_density,
        source="city_median",
    )


def load_city_csv(city: str) -> pd.DataFrame | None:
    """Load the per-tract CSV for a city if present.

    Expected columns: tract_code, lat, lon, income_household,
    income_per_capita, pct_foreign, population_density.
    """
    path = DATA_DIR / f"{city.lower()}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path} is missing columns {missing}. "
            f"Expected: {', '.join(REQUIRED_COLUMNS)} (see data/ine/README.md)."
        )
    # Income can be suppressed by INE for small tracts (statistical secrecy);
    # keep those rows for their population, impute income at join time.
    return df.dropna(subset=["lat", "lon", "population_density"]).reset_index(drop=True)


def _weighted(values: pd.Series, weights: pd.Series) -> float | None:
    ok = values.notna() & (weights > 0)
    if not ok.any():
        return None
    return float(np.average(values[ok], weights=weights[ok]))


def tract_demographics_for_hex(
    hex_lat: float,
    hex_lon: float,
    city: str,
    tracts: pd.DataFrame | None = None,
    radius_km: float = CATCHMENT_RADIUS_KM,
) -> ZoneDemographics:
    """Demographics of the hex's catchment (see module docstring)."""
    if tracts is None or tracts.empty:
        return city_defaults(city)

    # Local equirectangular distance (km); accurate to <0.1% at city scale.
    kx = 111.320 * math.cos(math.radians(hex_lat))
    dx = (tracts["lon"] - hex_lon) * kx
    dy = (tracts["lat"] - hex_lat) * 110.574
    dist = np.sqrt(dx * dx + dy * dy)
    fallback = city_defaults(city)

    if "population" in tracts.columns:
        inside = tracts[dist <= radius_km]
        pop = inside["population"].fillna(0)
        if pop.sum() > 0:
            inc_h = _weighted(inside["income_household"], pop)
            inc_p = _weighted(inside["income_per_capita"], pop)
            foreign = _weighted(inside["pct_foreign"], pop)
            return ZoneDemographics(
                income_household=inc_h if inc_h is not None else fallback.income_household,
                income_per_capita=inc_p if inc_p is not None else fallback.income_per_capita,
                pct_foreign=foreign if foreign is not None else fallback.pct_foreign,
                population_density=float(pop.sum()) / (math.pi * radius_km ** 2),
                source="ine_csv",
            )

    row = tracts.loc[dist.idxmin()]

    def val(col: str, default: float) -> float:
        v = row.get(col)
        return float(v) if v is not None and pd.notna(v) else default

    return ZoneDemographics(
        income_household=val("income_household", fallback.income_household),
        income_per_capita=val("income_per_capita", fallback.income_per_capita),
        pct_foreign=val("pct_foreign", fallback.pct_foreign),
        population_density=val("population_density", fallback.population_density),
        source="ine_csv",
    )
