"""Commercial rent per neighbourhood: loader + importer for licensed listings.

The pipeline reads `data/rent/<city>.csv`:

    neighbourhood,eur_per_sqm_month,n_listings,source

and Bayesian-shrinks each neighbourhood's figure toward the modelled rent
proxy by `n_listings` (see engine.estimate_rent_eur_per_sqm). The shipped
CSVs are author estimates calibrated to Cushman & Wakefield / CBRE Spain 2024
public report ranges (not figures published by those firms).

To use real listings you are licensed to use (a broker export, an
Idealista Data / Habitaclia data purchase, your own survey), put them in
a CSV and import them with `scripts/import_rent_listings.py`. This module
does no web scraping: portal terms of service forbid it, and Spanish
database rights protect listing data.

Listing CSV columns (case-insensitive):
    monthly_rent_eur, size_sqm, and either neighbourhood or lat + lon
"""
from __future__ import annotations

import csv
import re
import statistics
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..cities import get_city
from .neighborhoods import OUTSKIRTS, neighbourhood_for

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "rent"

# Listings outside this size band are almost always data-entry errors or
# warehouses; they are dropped before aggregation AND before counting.
MIN_SQM, MAX_SQM = 20.0, 2000.0
MIN_LISTINGS_PER_HOOD = 3


@dataclass
class RentListing:
    neighbourhood: str
    price_eur_month: float
    size_sqm: float

    @property
    def eur_per_sqm(self) -> float:
        return self.price_eur_month / self.size_sqm if self.size_sqm else 0.0


def normalise_name(name: str) -> str:
    """Join key for neighbourhood names from different sources.

    "Sarria-Sant Gervasi", "sarria-sant-gervasi" and "Sarrià Sant Gervasi"
    all map to "sarria sant gervasi".
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[-_'’/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---- importing licensed listings ----------------------------------------------


class ListingsError(ValueError):
    """The listings CSV is malformed (message says which row/column and how to fix)."""


def read_listings_csv(path: Path, city: str) -> tuple[list[RentListing], list[str]]:
    """Parse a listings CSV into RentListings with registry neighbourhood names.

    Returns (listings, warnings). Rows with a neighbourhood the city
    registry doesn't know, or coordinates outside every neighbourhood,
    are skipped and reported.
    """
    c = get_city(city)
    known = {normalise_name(h[0]): h[0] for h in c.hoods}
    listings: list[RentListing] = []
    warnings: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = {k.lower().strip(): k for k in (reader.fieldnames or [])}
        has_hood = "neighbourhood" in cols
        has_coords = "lat" in cols and "lon" in cols
        missing = [k for k in ("monthly_rent_eur", "size_sqm") if k not in cols]
        if missing or not (has_hood or has_coords):
            raise ListingsError(
                f"{path}: needs columns monthly_rent_eur, size_sqm and either neighbourhood "
                f"or lat+lon; got {reader.fieldnames}"
            )
        for i, row in enumerate(reader, start=2):
            try:
                price = float(str(row[cols["monthly_rent_eur"]]).replace(",", "."))
                size = float(str(row[cols["size_sqm"]]).replace(",", "."))
            except (TypeError, ValueError):
                warnings.append(f"row {i}: non-numeric rent/size, skipped")
                continue
            if has_hood and (row.get(cols["neighbourhood"]) or "").strip():
                hood = known.get(normalise_name(row[cols["neighbourhood"]]))
                if hood is None:
                    warnings.append(f"row {i}: unknown neighbourhood {row[cols['neighbourhood']]!r}, skipped")
                    continue
            elif has_coords:
                try:
                    hood = neighbourhood_for(city, float(row[cols["lat"]]), float(row[cols["lon"]]))
                except (TypeError, ValueError):
                    warnings.append(f"row {i}: bad lat/lon, skipped")
                    continue
                if hood == OUTSKIRTS:
                    warnings.append(f"row {i}: outside every named neighbourhood, skipped")
                    continue
            else:
                warnings.append(f"row {i}: no neighbourhood or coordinates, skipped")
                continue
            listings.append(RentListing(hood, price, size))
    return listings, warnings


def aggregate_by_neighbourhood(
    listings: Iterable[RentListing],
) -> dict[str, tuple[float, int]]:
    """{hood: (median EUR/sqm/month, n_listings used)}.

    Listings outside [MIN_SQM, MAX_SQM] are dropped before both the median
    and the count, so n_listings is the sample the median came from.
    Hoods with fewer than MIN_LISTINGS_PER_HOOD listings are omitted.
    """
    by_hood: dict[str, list[float]] = {}
    for lst in listings:
        if lst.size_sqm < MIN_SQM or lst.size_sqm > MAX_SQM:
            continue
        by_hood.setdefault(lst.neighbourhood, []).append(lst.eur_per_sqm)
    return {
        h: (statistics.median(v), len(v))
        for h, v in by_hood.items() if len(v) >= MIN_LISTINGS_PER_HOOD
    }


def write_city_csv(city: str, listings: list[RentListing], source: str) -> Path | None:
    """Write the per-neighbourhood median rent CSV. Returns path, or None if nothing qualified."""
    agg = aggregate_by_neighbourhood(listings)
    if not agg:
        return None
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{city.lower()}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["neighbourhood", "eur_per_sqm_month", "n_listings", "source"])
        for hood, (rent, n) in sorted(agg.items()):
            w.writerow([hood, f"{rent:.2f}", n, source])
    return path


# ---- loading ---------------------------------------------------------------------


def load_city_csv(city: str) -> dict[str, float] | None:
    """Load per-hood median rent map (normalised name -> rent), if present."""
    full = load_city_csv_full(city)
    if not full:
        return None
    return {h: v[0] for h, v in full.items()}


def load_city_csv_full(city: str) -> dict[str, tuple[float, int]] | None:
    """Load per-hood (rent, n_listings), keyed by `normalise_name(neighbourhood)`."""
    path = OUT_DIR / f"{city.lower()}.csv"
    if not path.exists():
        return None
    out: dict[str, tuple[float, int]] = {}
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                rent = float(row["eur_per_sqm_month"])
                n = int(row.get("n_listings") or 0)
                out[normalise_name(row["neighbourhood"])] = (rent, n)
            except (KeyError, ValueError):
                continue
    return out or None


def rent_source(city: str) -> str:
    """The rent CSV's `source` column, 'unknown' if absent, 'none' if no CSV.

    Shipped CSVs say `seeded_cw_cbre_2024`; imports carry the label passed
    to scripts/import_rent_listings.py.
    """
    path = OUT_DIR / f"{city.lower()}.csv"
    if not path.exists():
        return "none"
    with path.open("r", encoding="utf-8") as f:
        first = next(csv.DictReader(f), None)
    return (first or {}).get("source") or "unknown"
