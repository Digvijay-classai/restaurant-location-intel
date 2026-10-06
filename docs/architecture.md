# Architecture

## High-level flow

```
                       ┌──────────── src/cities.py · src/cuisines.py ────────────┐
                       │ registries: centres, neighbourhoods, crime, tourism,     │
                       │ income medians, INE table ids, licence zones;            │
                       │ cuisine aliases, Places types, tickets, daypart          │
                       └───────┬───────────────────┬─────────────────────────────┘
scripts/pull_live_data ─┐      │                   │
                        ├──▶ pipeline.build_base_frame  (Overpass + INE [+ Places])
pipeline (no snapshot) ─┘      │
scripts/build_demo_data ──▶ synthetic frame
                               ▼
        data/sample_output/<city>_demo.json   {meta: sources+vintages, hexes: [...]}
                               ▼
        pipeline.run_pipeline_with_meta(city, cuisine, budget, weights, size_sqm)
            └─ score_frame: _enrich (same_cuisine, neighbourhood, crime, rent join)
                             → engine.score_hexes      8 components + confidence + composite
                             → financial_model.compute  economics + sensitivity + risk flags
                             → financial_model.rank_zones   one economics-first rank
                               ▼
        app.py: provenance bar → anchor card → Shortlist | Map | Rankings | Method | Data
                  (viz/maps.py, viz/theme.py, formatting.py, export.py)
```

## Key design decisions

**1. H3 hex grid over admin boundaries.** Resolution 8 gives consistent
~0.74 km² units and clean spatial joins. Scoring also accepts non-H3 ids
(they simply get no neighbour term), which keeps a future
listing-by-address mode cheap.

**2. Snapshots are committed data with provenance.** Each snapshot has a
`meta` block: `sources` (pois, demographics, competitors, boundary) and
`vintages`. The app reads provenance from it. It does not infer anything
from whether the file exists. `build_demo_data.py` refuses to overwrite a
LIVE snapshot unless you pass `--force`, and CI validates snapshots but
never regenerates them.

**3. One builder.** `pipeline.build_base_frame` is the only code that turns
raw sources into a hex frame. The app's live fallback and
`pull_live_data.py` both call it.

**4. Pure scoring layer.** `src/scoring/` does no I/O (apart from the
pipeline's rent CSV join). Component functions take and return pandas
objects and preserve the caller's index.

**5. Economics-first ranking.** The composite and the economics are
independent views. The rank comes from economics, and the composite breaks
ties. Map pins, the table and the briefs all use the same `rank`.

**6. Verdicts are gated on data quality.** `pipeline.verdicts_allowed(meta)`
requires live POIs and INE tract demographics.

**7. Caching.**
- Overpass raw responses: `data/cache/osm_<city>.json` (gitignored; a
  corrupt file is re-downloaded).
- Google Places: SQLite `data/cache/places.sqlite` keyed by
  `(hex_id, cuisine, radius)`. Used only during a private refresh
  (`--places` writes to `data/private/`), never on page load. CI rejects
  committed Places data, and the app hides its map for such snapshots
  (Google Maps Platform terms).
- App: `st.cache_data` keyed on every input (city, cuisine, budget,
  weights, size).

## Module map

| Module | Responsibility |
|--------|----------------|
| `src/cities.py` | City registry (one entry per city) + data vintages |
| `src/cuisines.py` | Cuisine registry + exact OSM tag matching |
| `src/geo/boundaries.py` | City polygon from GeoJSON, or bbox fallback |
| `src/geo/grid.py` | H3 grid over a polygon |
| `src/geo/distance.py` | Haversine |
| `src/data_sources/overture_maps.py` | OSM via Overpass (nodes, ways, relations) → hex counts |
| `src/data_sources/google_places.py` | Places (New) counts with SQLite cache |
| `src/data_sources/ine_demographics.py` | INE tract CSV loader, 1 km catchment join, city-median fallback |
| `src/data_sources/ine_api.py` | INE ADRH section polygons (ArcGIS) + Tempus tables → tract CSV |
| `src/data_sources/rent_listings.py` | Rent CSV loader (normalised names), licensed-listings importer |
| `src/data_sources/{crime,tourism,neighborhoods}.py` | Registry lookups |
| `src/scoring/weights.py` | Weight profiles, budget tiers |
| `src/scoring/engine.py` | Input validation, ring smoothing, components, composite |
| `src/scoring/financial_model.py` | Economics, sensitivity, risk flags, ranking, deal brief |
| `src/pipeline.py` | Snapshot I/O + validation, builder, `score_frame`, provenance helpers |
| `src/export.py` | Strict-JSON GeoJSON export |
| `src/formatting.py` | es-ES number/€ formatting |
| `src/viz/maps.py`, `src/viz/theme.py` | Folium map, colour tokens, CVD-safe ramp |
| `app.py` | Streamlit UI |
| `scripts/pull_live_data.py` | LIVE snapshot refresh |
| `scripts/build_demo_data.py` | SYNTHETIC snapshots (deterministic) |
| `scripts/fetch_ine_tracts.py` | INE census-tract demographics → `data/ine/<city>.csv` |
| `scripts/import_rent_listings.py` | Licensed rent listings → `data/rent/<city>.csv` |
| `scripts/validate_snapshots.py` | Snapshot schema check (CI) |

## Deployment

- **Streamlit Community Cloud:** point it at `app.py`. Snapshots are
  committed, so first paint needs no network and no secrets.
- **Theme:** pinned in `.streamlit/config.toml`. Keep it in sync with
  `src/viz/theme.py`.
- **Refreshing data** is an offline job: run `pull_live_data.py`, commit the
  snapshot, and CI validates it.
