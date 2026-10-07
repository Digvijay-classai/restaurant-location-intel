# Changelog

## 0.4.0 (2026-10-07)

### Added
- **Home page** that explains what the tool answers, shows live coverage
  numbers computed from the shipped data, gives a 4-step "how to use" guide
  and "how to read the results", and links to three one-click example
  scenarios (one of them shows the tool saying "no").
- **Multi-page navigation** (Home · Analyse · Methodology · Data & legal),
  with a Home link at the top of the sidebar. Inputs persist across pages.
- Methodology and Data & legal pages render the repo docs, a single source
  of truth, with relative links rewritten to GitHub.
- CI tests the latest allowed dependency versions on Python 3.12, 3.13 and
  3.14 (what Streamlit Community Cloud installs), plus a weekly run.

### Changed
- The provenance bar shows the current crime source; the unused tourism
  figures are no longer displayed.
- New screenshots (Home, Analyse, map crop).

## 0.3.0 (2026-10-06)

Fixes from the /autoplan audit. Several of these changed scores, so
rankings differ from 0.2.

### Fixed
- **Edge smoothing never ran.** Under h3 v4, `grid_disk` returns a list. The
  resulting TypeError was swallowed by a bare `except`, so competition,
  ecosystem, foot traffic and tourism ignored neighbouring hexes. Missing
  neighbours at the edge of the study area are now imputed.
- **Weight sliders had no effect.** Weights are now passed into scoring.
- **The header could show one city over another city's data** after
  changing inputs without pressing Analyze. The app now recomputes on every
  input change, and the Analyze button is gone.
- **Revenue rose with competition.** Demand now shrinks with each
  same-cuisine competitor nearby. The composite no longer feeds revenue
  (the `tilt` double count is removed).
- **Scoring a sliced frame produced NaN composites** (index misalignment).
  NaN income or an empty frame no longer crash scoring or the deal brief.
- **Licence/BIC flags were keyed by name only.** Valladolid "Centro" got
  Madrid's flag. Flags are now per city.
- **Cuisine matching used substrings.** "latin_american" counted as burger.
  Matching now uses exact tokens.
- **Constant offsets squashed every city's composite** into ~47-80.
- **Missing tract data used a flat 5,000 people/km² everywhere**, a third of
  Barcelona's real density. The fallback is now each city's municipal density,
  still labelled as estimated.
- **Zero demand produced a €0 ticket** and a 12,264-cover break-even.
- **GeoJSON export wrote `Infinity`**, which is invalid JSON.
- **The synthetic demo data was random per process.** It was seeded with
  `hash()`; it now uses crc32.
- **`pull_live_data.py` crashed** with `ModuleNotFoundError: src`.
- **Overpass rejected requests** with HTTP 406 because of the default
  python-requests User-Agent.
- **Overpass queried nodes only**, so restaurants and shops mapped as
  buildings were missed. It now queries nodes, ways and relations.
- **Imported rent listings could not join neighbourhood names**
  (accents and hyphens). `n_listings` was also counted before the size filter.
- **Google Places was never called**, even though the UI said it was. The
  adapter also sent `textQuery`, which `searchNearby` ignores. It now uses
  the Places cuisine types.

### Added
- **INE census-tract demographics** for Barcelona, Madrid and Valladolid
  (2023: population, net income, foreign share; 4,348 tracts), fetched
  with `scripts/fetch_ine_tracts.py` from INE's free ADRH map service and
  Tempus API. Hexes aggregate the tracts within the 1 km revenue
  catchment. This unlocks verdicts for all three cities.
- Snapshot `meta` with per-source provenance and vintages, and a
  provenance bar in the app. Verdicts are withheld unless POIs are live and
  demographics come from INE tracts.
- Economics-first ranking shared by the map pins, the table and the briefs.
- Seat-capacity cap, labour that scales per cover, and size-aware rent,
  capex and seats. Premises size is editable in the sidebar.
- Downside and upside sensitivity in every brief.
- `src/cities.py` and `src/cuisines.py` registries, so adding a city is one entry.
- `pull_live_data.py --places` (Google Places counts) and `--no-cache`;
  `build_demo_data.py --city/--force` (never overwrites LIVE data
  silently); `scripts/validate_snapshots.py`.
- Colour-blind-safe viridis map ramp with tick labels, a pinned theme,
  es-ES number and € formatting, and a defined empty state for every view.
- Live OpenStreetMap snapshots for Barcelona, Madrid and Valladolid.
- 90+ tests: real-H3 regression tests, economics, ranking, a golden
  ranking, offline pipeline, scripts, and Streamlit AppTest UI flows.
- `requirements.lock`, `requirements-dev.txt`, `pyproject.toml`
  (`pip install -e .`), `.python-version` and a `Makefile`.

### Changed (legal compliance for public release)
- **Idealista scraper replaced by `scripts/import_rent_listings.py`**, which
  imports listings you are licensed to use. The aggregation, name matching
  and shrinkage are unchanged. Portal terms forbid scraping.
- **Google Places output is private by default** (`data/private/`, gitignored).
  CI rejects committed Places data, and the app hides its map and credits
  Google when one is loaded (Google Maps Platform terms).
- **Basemap switched from Esri to the OpenStreetMap standard tiles** (no key;
  darkened with a CSS filter), with OpenStreetMap and INE attribution on the
  map and in the app footer. CARTO was tried, but it now requires an API key.
- Added `DISCLAIMER.md` and `DATA_LICENSES.md` (per-source licence and
  attribution; snapshots under ODbL), plus an in-app disclaimer and
  privacy note. Streamlit usage statistics are disabled.

- **Crime uses official 2025 municipal counts** (Ministerio del Interior,
  Balance de Criminalidad Q4 2025) divided by INE population: Barcelona
  95.2, Madrid 60.5, Valladolid 28.1 per 1,000. The previous unsourced rates
  were 73.4, 61.2 and 42.1. Neighbourhood variation is kept as a relative
  index, labelled as an author estimate.
- **Rent attribution corrected**: the neighbourhood figures are author
  estimates calibrated to C&W / CBRE ranges, not figures cited from them.

### Removed
- `geopandas` and `plotly` (unused).
- CI no longer regenerates snapshots. It validates the committed ones.
