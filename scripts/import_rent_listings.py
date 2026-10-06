"""Import commercial-rent listings you are licensed to use into data/rent/<city>.csv.

Usage:
    python scripts/import_rent_listings.py barcelona listings.csv --source broker_export_2026-10

The listings CSV needs columns `monthly_rent_eur`, `size_sqm` and either
`neighbourhood` (matched to src/cities.py names, accent/hyphen-insensitive)
or `lat` + `lon` (assigned to the nearest named neighbourhood). Listings
outside 20-2,000 sqm are ignored; neighbourhoods need >= 3 listings.

The pipeline blends each neighbourhood's median with the modelled rent,
weighted by listing count. Only import data you have the right to use
(broker exports, purchased Idealista Data / Habitaclia feeds, your own
survey). Do not scrape listing portals.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import _bootstrap  # noqa: F401  (adds repo root to sys.path)
except ImportError:  # run as `python -m scripts.<name>`
    from scripts import _bootstrap  # noqa: F401

from src.cities import CITY_KEYS
from src.data_sources import rent_listings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Import licensed rent listings for a city.")
    p.add_argument("city", choices=CITY_KEYS)
    p.add_argument("listings", type=Path, help="CSV of individual listings.")
    p.add_argument("--source", required=True,
                   help="Provenance label shown in the app, e.g. broker_export_2026-10.")
    args = p.parse_args(argv)

    try:
        listings, warnings = rent_listings.read_listings_csv(args.listings, args.city)
    except (rent_listings.ListingsError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for w in warnings[:20]:
        print(f"warning: {w}")
    if len(warnings) > 20:
        print(f"warning: ... {len(warnings) - 20} more")

    path = rent_listings.write_city_csv(args.city, listings, args.source)
    if path is None:
        print(f"error: no neighbourhood had >= {rent_listings.MIN_LISTINGS_PER_HOOD} usable "
              "listings; nothing written.", file=sys.stderr)
        return 1
    n_hoods = len(rent_listings.load_city_csv_full(args.city) or {})
    print(f"wrote {path}  ({len(listings)} listings -> {n_hoods} neighbourhoods, source={args.source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
