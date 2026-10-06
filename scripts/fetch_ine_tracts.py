"""Download census-tract demographics for a city from INE (free, no key).

Run:
    python scripts/fetch_ine_tracts.py barcelona
    python scripts/pull_live_data.py barcelona      # then rebuild the snapshot

Writes data/ine/<city>.csv: one row per seccion censal inside the city's
bounding box (neighbouring municipalities included) with population,
density, net household and per-person income, and foreign-national share,
plus the year of each figure. Sources: INE ADRH (Atlas de Distribucion de
Renta de los Hogares) section polygons + Tempus tables; see
src/data_sources/ine_api.py.
"""
from __future__ import annotations

import argparse
import sys

try:
    import _bootstrap  # noqa: F401  (adds repo root to sys.path)
except ImportError:  # run as `python -m scripts.<name>`
    from scripts import _bootstrap  # noqa: F401

import pandas as pd

from src.cities import CITIES, CITY_KEYS
from src.data_sources import ine_api
from src.data_sources.ine_demographics import DATA_DIR


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fetch INE census-tract demographics for a city.")
    p.add_argument("city", choices=CITY_KEYS)
    args = p.parse_args(argv)
    c = CITIES[args.city]
    if not (c.ine_population_table and c.ine_income_table):
        print(f"error: set ine_population_table / ine_income_table for {args.city} in "
              "src/cities.py (ids from https://servicios.ine.es/wstempus/js/ES/TABLAS_OPERACION/353)",
              file=sys.stderr)
        return 2

    try:
        print(f"[ine] section polygons around {c.name} ...")
        sections = ine_api.sections_frame(ine_api.fetch_section_features(c.center, c.radius_deg))
        print(f"[ine] {len(sections)} sections; downloading ADRH tables "
              f"{c.ine_population_table} + {c.ine_income_table} (a few MB each) ...")
        stats = pd.concat([
            ine_api.parse_series(ine_api.fetch_table(c.ine_population_table),
                                 [ine_api.POPULATION, ine_api.PCT_SPANISH]),
            ine_api.parse_series(ine_api.fetch_table(c.ine_income_table),
                                 [ine_api.INCOME_HOUSEHOLD, ine_api.INCOME_PERSON]),
        ])
    except ine_api.INEError as exc:
        print(f"error: {exc}\nNothing was written.", file=sys.stderr)
        return 1

    tracts = ine_api.build_tract_frame(sections, stats)
    if tracts.empty:
        print("error: no sections matched INE statistics; nothing written.", file=sys.stderr)
        return 1
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{args.city}.csv"
    tracts.to_csv(path, index=False)
    print(f"wrote {path}  ({len(tracts)} of {len(sections)} sections with population; "
          f"{int(tracts['population'].sum()):,} residents; "
          f"income missing for {int(tracts['income_household'].isna().sum())}; "
          f"population year {int(tracts['population_year'].max())}, "
          f"income year {int(tracts['income_year'].max())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
