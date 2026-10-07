"""End-to-end pipeline: boundary -> hex grid -> POIs -> demographics -> scores -> economics.

```
build_base_frame(city)            (live: Overpass + INE CSV [+ Google Places])
        │  or                       one builder, used by the app AND scripts
load_snapshot(city)               data/sample_output/<city>_demo.json {meta, hexes}
        ▼
_enrich: same_cuisine (from cuisine_counts), neighbourhood, crime, rent join
        ▼
engine.score_hexes  ──▶  financial_model.compute  ──▶  financial_model.rank_zones
```

Every snapshot carries a `meta` block recording where each input came
from (synthetic / live OSM / INE / city median / Google Places) and its
vintage, so the UI can show provenance and gate verdicts on it.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .cities import CRIME_VINTAGE, DENSITY_VINTAGE, INCOME_VINTAGE, TRACT_VINTAGE, get_city
from .cuisines import CUISINES
from .data_sources import crime, ine_demographics, neighborhoods, overture_maps, rent_listings, tourism
from .data_sources.overture_maps import POI_CATEGORIES
from .geo.boundaries import boundary_source, load_city_boundary
from .geo.grid import generate_hex_grid
from .scoring import financial_model
from .scoring.engine import ScoreInputs, score_hexes

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
# RLI_SNAPSHOT_DIR lets you point the app at private snapshots (e.g. ones with
# Google Places data, which must not be published) without touching the repo.
SAMPLE_DIR = Path(os.environ.get("RLI_SNAPSHOT_DIR") or ROOT / "data" / "sample_output")
if not SAMPLE_DIR.is_absolute():
    SAMPLE_DIR = ROOT / SAMPLE_DIR
PRIVATE_DIR = ROOT / "data" / "private"
SNAPSHOT_SCHEMA_VERSION = 2

# Source labels used in snapshot meta.
SYNTHETIC = "synthetic"
LIVE_OSM = "osm_overpass"
GOOGLE_PLACES = "google_places"

REQUIRED_HEX_KEYS = ("h3_id", "center_lat", "center_lon", *POI_CATEGORIES,
                     "cuisine_counts", "income_household", "population_density",
                     "demographics_source")


@dataclass
class PipelineResult:
    df: pd.DataFrame
    meta: dict


# ---- snapshots ----------------------------------------------------------------


def precomputed_path(city: str) -> Path:
    return SAMPLE_DIR / f"{city.lower()}_demo.json"


def has_precomputed(city: str) -> bool:
    return precomputed_path(city).exists()


def _legacy_meta(payload: dict) -> dict:
    """Meta for snapshots written before schema v2 (no meta block)."""
    synthetic = "build_demo_data" in str(payload.get("generated_with", ""))
    return {
        "schema_version": 1,
        "city": payload.get("city"),
        "resolution": payload.get("resolution", 8),
        "generated_with": payload.get("generated_with", "unknown"),
        "generated_at": None,
        "sources": {
            "pois": SYNTHETIC if synthetic else LIVE_OSM,
            "demographics": SYNTHETIC if synthetic else "unknown",
            "competitors": SYNTHETIC if synthetic else "osm",
            "boundary": "bbox",
        },
        "vintages": {},
    }


def validate_snapshot(payload: dict) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems: list[str] = []
    meta = payload.get("meta")
    if meta is None:
        problems.append("missing 'meta' block (schema v2)")
    else:
        for key in ("city", "sources", "vintages", "generated_with"):
            if key not in meta:
                problems.append(f"meta missing '{key}'")
        for key in ("pois", "demographics", "competitors"):
            if key not in meta.get("sources", {}):
                problems.append(f"meta.sources missing '{key}'")
    hexes = payload.get("hexes")
    if not isinstance(hexes, list) or not hexes:
        problems.append("'hexes' must be a non-empty list")
        return problems
    for i, h in enumerate(hexes):
        missing = [k for k in REQUIRED_HEX_KEYS if k not in h]
        if missing:
            problems.append(f"hex {i} ({h.get('h3_id')}) missing {missing}")
            break
    ids = [h.get("h3_id") for h in hexes]
    if len(set(ids)) != len(ids):
        problems.append("duplicate h3_id values")
    return problems


def load_snapshot(city: str) -> PipelineResult:
    path = precomputed_path(city)
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Snapshot {path} is unreadable ({exc}). Rebuild it with "
            f"`python scripts/pull_live_data.py {city}` or "
            f"`python scripts/build_demo_data.py --city {city} --force`."
        ) from exc
    meta = payload.get("meta") or _legacy_meta(payload)
    return PipelineResult(pd.DataFrame(payload["hexes"]), meta)


def load_precomputed(city: str) -> pd.DataFrame:
    """Backwards-compatible: just the hex frame."""
    return load_snapshot(city).df


def write_snapshot(city: str, df: pd.DataFrame, meta: dict, path: Path | None = None) -> Path:
    path = path or precomputed_path(city)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "hexes": json.loads(df.to_json(orient="records"))}
    problems = validate_snapshot(payload)
    if problems:
        raise ValueError(f"Refusing to write invalid snapshot for {city}: {problems}")
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    return path


def existing_snapshot_source(city: str) -> str | None:
    """sources.pois of the snapshot on disk, or None if there is none."""
    if not has_precomputed(city):
        return None
    try:
        return load_snapshot(city).meta.get("sources", {}).get("pois")
    except ValueError:
        return None


# ---- live base frame (the single builder) ------------------------------------


def build_base_frame(
    city: str,
    resolution: int = 8,
    with_places: bool = False,
    use_cache: bool = True,
) -> PipelineResult:
    """Live pipeline: Overpass POIs + INE tracts (+ optional Google Places).

    Raises overture_maps.OverpassError / google_places.PlacesError with an
    actionable message on failure; nothing is written here.
    """
    get_city(city)  # validates the name with a helpful error
    boundary = load_city_boundary(city)
    cells = generate_hex_grid(boundary, resolution)
    pois = overture_maps.fetch_pois(city, boundary, use_cache=use_cache)
    counts = overture_maps.pois_to_hex_counts(pois, resolution)
    tracts = ine_demographics.load_city_csv(city)

    empty = {**{k: 0 for k in POI_CATEGORIES}, "cuisine_counts": {k: 0 for k in CUISINES}}
    rows = []
    for c in cells:
        poi_row = counts.get(c.h3_id, empty)
        demo = ine_demographics.tract_demographics_for_hex(c.center_lat, c.center_lon, city, tracts)
        rows.append({
            "h3_id": c.h3_id,
            "center_lat": c.center_lat,
            "center_lon": c.center_lon,
            **{k: int(poi_row.get(k, 0)) for k in POI_CATEGORIES},
            "cuisine_counts": dict(poi_row["cuisine_counts"]),
            "income_household": demo.income_household,
            "income_per_capita": demo.income_per_capita,
            "pct_foreign": demo.pct_foreign,
            "population_density": demo.population_density,
            "demographics_source": demo.source,
        })
    df = pd.DataFrame(rows)

    competitors = "osm"
    if with_places:
        from .data_sources import google_places
        places_cz, places_all = [], []
        for r in df.itertuples():
            places_cz.append({
                cz: google_places.count_restaurants(r.center_lat, r.center_lon, r.h3_id, cz)
                for cz in CUISINES
            })
            places_all.append(google_places.count_restaurants(r.center_lat, r.center_lon, r.h3_id))
        df["places_cuisine_counts"] = places_cz
        df["places_restaurant"] = places_all
        competitors = GOOGLE_PLACES

    demo_sources = set(df["demographics_source"]) if len(df) else {"city_median"}
    meta = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "city": city.lower(),
        "resolution": resolution,
        "generated_with": "src.pipeline.build_base_frame",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "pois": LIVE_OSM,
            "demographics": demo_sources.pop() if len(demo_sources) == 1 else "mixed",
            "competitors": competitors,
            "boundary": boundary_source(city),
        },
        "vintages": {
            "pois": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "income": (TRACT_VINTAGE if "ine_csv" in set(df["demographics_source"])
                       else "city median, " + INCOME_VINTAGE),
            "density": (TRACT_VINTAGE if "ine_csv" in set(df["demographics_source"])
                        else DENSITY_VINTAGE),
            "crime": CRIME_VINTAGE,
        },
        "n_pois": len(pois),
    }
    return PipelineResult(df, meta)


# ---- enrichment + scoring -----------------------------------------------------


def _enrich(base: pd.DataFrame, city: str, cuisine: str, meta: dict) -> pd.DataFrame:
    base = base.copy()
    use_places = (meta.get("sources", {}).get("competitors") == GOOGLE_PLACES
                  and "places_cuisine_counts" in base.columns)
    if use_places:
        base["restaurant_osm"] = base["restaurant"]
        base["restaurant"] = base["places_restaurant"].fillna(base["restaurant"]).astype(int)
        counts_col = "places_cuisine_counts"
    else:
        counts_col = "cuisine_counts"
    if counts_col in base.columns:
        base["same_cuisine"] = base[counts_col].apply(
            lambda d: int((d or {}).get(cuisine, 0)) if isinstance(d, dict) else 0
        )
    elif "same_cuisine" not in base.columns:
        base["same_cuisine"] = 0
    base["competitor_source"] = GOOGLE_PLACES if use_places else meta.get("sources", {}).get("competitors", "osm")

    base["neighbourhood"] = [
        neighborhoods.neighbourhood_for(city, lat, lon)
        for lat, lon in zip(base["center_lat"], base["center_lon"])
    ]
    base["crime_per_1000"] = base["neighbourhood"].map(
        lambda h: crime.neighbourhood_crime_rate(city, h)
    )

    listings = rent_listings.load_city_csv_full(city)
    keys = base["neighbourhood"].map(rent_listings.normalise_name)
    if listings:
        base["listing_rent"] = keys.map(lambda k: listings[k][0] if k in listings else None)
        base["listing_n"] = keys.map(lambda k: listings[k][1] if k in listings else 0)
        base["rent_source"] = base["listing_rent"].map(
            lambda v: "listings+model" if pd.notna(v) else "model"
        )
    else:
        base["listing_rent"] = None
        base["listing_n"] = 0
        base["rent_source"] = "model"
    return base


def score_frame(
    base: pd.DataFrame,
    meta: dict,
    city: str,
    cuisine: str,
    budget: str,
    weights: Mapping[str, float] | None = None,
    size_sqm: float = financial_model.REFERENCE_SIZE_SQM,
) -> pd.DataFrame:
    """Enrich, score, cost and rank a base hex frame (no I/O besides the rent CSV)."""
    enriched = _enrich(base, city, cuisine, meta)
    muni = tourism.municipality_tourism(city)
    inputs = ScoreInputs(
        cuisine=cuisine,
        budget=budget,
        hotel_beds_per_1000=muni["hotel_beds_per_1000"],
        overnight_stays_per_capita=muni["overnight_stays_per_capita"],
        weights=weights,
    )
    scored = score_hexes(enriched, inputs)
    scored = financial_model.compute(scored, cuisine, city=city, size_sqm=size_sqm, budget=budget)
    return financial_model.rank_zones(scored)


def run_pipeline_with_meta(
    city: str,
    cuisine: str,
    budget: str,
    weights: Mapping[str, float] | None = None,
    size_sqm: float = financial_model.REFERENCE_SIZE_SQM,
    resolution: int = 8,
    use_precomputed_grid: bool = True,
) -> PipelineResult:
    """Scored, costed and ranked hex table for (city, cuisine, budget) plus provenance."""
    city = city.lower()
    if use_precomputed_grid and has_precomputed(city):
        snap = load_snapshot(city)
    else:
        log.info("No snapshot for %s; building live (Overpass)", city)
        snap = build_base_frame(city, resolution)
    meta = dict(snap.meta)
    meta["rent"] = rent_listings.rent_source(city)
    df = score_frame(snap.df, meta, city, cuisine, budget, weights, size_sqm)
    return PipelineResult(df, meta)


def run_pipeline(
    city: str,
    cuisine: str,
    budget: str,
    weights: Mapping[str, float] | None = None,
    size_sqm: float = financial_model.REFERENCE_SIZE_SQM,
    resolution: int = 8,
    use_precomputed_grid: bool = True,
) -> pd.DataFrame:
    """Scored, costed and ranked hex table (see run_pipeline_with_meta)."""
    return run_pipeline_with_meta(city, cuisine, budget, weights, size_sqm,
                                  resolution, use_precomputed_grid).df


# ---- provenance helpers -------------------------------------------------------

CORE_REAL_SOURCES = {"pois": {LIVE_OSM}, "demographics": {"ine_csv"}}


def verdicts_allowed(meta: dict) -> bool:
    """Go/no-go verdicts only when POIs are live and demographics are measured."""
    sources = meta.get("sources", {})
    return all(sources.get(k) in ok for k, ok in CORE_REAL_SOURCES.items())


def is_synthetic(meta: dict) -> bool:
    return SYNTHETIC in meta.get("sources", {}).values()
