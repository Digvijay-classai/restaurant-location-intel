"""Generate SYNTHETIC demo snapshots (offline, no network).

The output is randomly generated from a seeded model calibrated against
public ranges (INE 2022-2024, Cushman & Wakefield / CBRE Spain 2024). It is
labelled `sources.pois = "synthetic"` in the snapshot meta, and the app
shows a SYNTHETIC banner and withholds verdicts for it.

Real data: `python scripts/pull_live_data.py <city>`.

Run:
    python scripts/build_demo_data.py                 # all cities without a LIVE snapshot
    python scripts/build_demo_data.py --city madrid   # one city
    python scripts/build_demo_data.py --force         # also overwrite LIVE snapshots

Deterministic: the same city always produces the same snapshot (seeded
with crc32 of the city name, not Python's per-process salted hash()).
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import zlib

try:
    import _bootstrap  # noqa: F401  (adds repo root to sys.path)
except ImportError:  # run as `python -m scripts.<name>`
    from scripts import _bootstrap  # noqa: F401

import h3
import pandas as pd
from h3 import LatLngPoly

from src.cities import CITIES, CITY_KEYS, CRIME_VINTAGE
from src.cuisines import CUISINES
from src.geo.distance import haversine_km
from src.pipeline import (LIVE_OSM, SNAPSHOT_SCHEMA_VERSION, SYNTHETIC,
                          existing_snapshot_source, write_snapshot)

RES = 8


def city_seed(city: str) -> int:
    return zlib.crc32(city.encode("utf-8"))


def _grid(city: str) -> list[str]:
    c = CITIES[city]
    lat, lon = c.center
    r = c.synthetic_radius_deg
    poly = LatLngPoly([(lat - r, lon - r), (lat - r, lon + r),
                       (lat + r, lon + r), (lat + r, lon - r)])
    return sorted(h3.polygon_to_cells(poly, RES))


def generate_city(city: str) -> pd.DataFrame:
    c = CITIES[city]
    rng = random.Random(city_seed(city))
    clat, clon = c.center
    rows = []
    for hid in _grid(city):
        lat, lon = h3.cell_to_latlng(hid)
        core = math.exp(-haversine_km(lat, lon, clat, clon) / 2.2)

        restaurants = max(0, int(rng.gauss(28 * core + 2, 7 * core + 2)))
        shops       = max(0, int(rng.gauss(45 * core + 3, 12 * core + 3)))
        offices     = max(0, int(rng.gauss(18 * core + 1, 6 * core + 1)))
        transit     = max(0, int(rng.gauss(2.5 * core,     1.0)))
        bus_stops   = max(0, int(rng.gauss(6 * core + 1,   2.0)))
        tourism_poi = max(0, int(rng.gauss(5 * core,       2.5)))
        hotels      = max(0, int(rng.gauss(3 * core,       1.5)))
        nightlife   = max(0, int(rng.gauss(4 * core,       2.0)))

        angle = math.atan2(lat - clat, lon - clon)
        wealth_trend = math.cos(angle * 2 + rng.random() * 0.1)
        income = (c.income_household + 0.35 * c.synthetic_income_sd * wealth_trend
                  + rng.gauss(0, 0.25 * c.synthetic_income_sd))
        income = max(14_000.0, income)

        cuisine_counts = {}
        for cz in CUISINES:
            lam = c.synthetic_cuisine_share.get(cz, 0.05) * restaurants * 0.35
            cuisine_counts[cz] = max(0, int(rng.gauss(lam, max(0.6, lam * 0.6))))

        rows.append({
            "h3_id": hid,
            "center_lat": lat,
            "center_lon": lon,
            "restaurant": restaurants,
            "shop": shops,
            "transit": transit,
            "bus_stop": bus_stops,
            "tourism": tourism_poi,
            "hotel": hotels,
            "office": offices,
            "nightlife": nightlife,
            "cuisine_counts": cuisine_counts,
            "income_household": round(income, 0),
            "income_per_capita": round(income / 2.35, 0),
            "pct_foreign": max(2.0, min(45.0, rng.gauss(c.pct_foreign, 6.0))),
            "population_density": max(300.0, rng.gauss(12_000 * core + 3_000, 2_500)),
            "demographics_source": SYNTHETIC,
        })
    return pd.DataFrame(rows)


def synthetic_meta(city: str) -> dict:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "city": city,
        "resolution": RES,
        "generated_with": "scripts/build_demo_data.py",
        "generated_at": None,  # deterministic output: no timestamp
        "sources": {"pois": SYNTHETIC, "demographics": SYNTHETIC,
                    "competitors": SYNTHETIC, "boundary": "bbox"},
        "vintages": {"pois": "synthetic", "income": "synthetic",
                     "crime": CRIME_VINTAGE},
        "note": ("SYNTHETIC demo snapshot: randomly generated, calibrated against public "
                 "ranges. Not real market data. Replace with scripts/pull_live_data.py."),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate SYNTHETIC demo snapshots (no network).")
    p.add_argument("--city", choices=CITY_KEYS, action="append",
                   help="City to build (repeatable). Default: all cities.")
    p.add_argument("--force", action="store_true",
                   help="Overwrite snapshots built from live data (otherwise they are kept).")
    args = p.parse_args(argv)

    for city in args.city or CITY_KEYS:
        if existing_snapshot_source(city) == LIVE_OSM and not args.force:
            print(f"skip {city}: existing snapshot is LIVE data (pass --force to replace it "
                  "with synthetic data)")
            continue
        df = generate_city(city)
        path = write_snapshot(city, df, synthetic_meta(city))
        print(f"wrote {path}  ({len(df)} hexes, SYNTHETIC)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
