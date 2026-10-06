# Contributing

Thanks for your interest. The project is deliberately small and modular;
new contributions should keep it that way.

## Development setup

```bash
python -m venv .venv            # Python 3.9+ (CI uses 3.11, see .python-version)
source .venv/bin/activate
pip install -r requirements.lock   # exact tested versions incl. pytest
pip install -e .                   # optional: makes `src` importable from anywhere
make test                          # or: python -m pytest -q
make run                           # or: streamlit run app.py
```

## Adding a city

Every per-city value lives in one place, `src/cities.py`.

1. Add a `City(...)` entry to `CITIES` in `src/cities.py`:
   - centre and bbox radius;
   - neighbourhood centroids with radii;
   - crime per 1,000 residents (city and per neighbourhood);
   - hotel beds per 1,000 residents and overnight stays per capita;
   - city-median income;
   - INE ADRH table ids (for `fetch_ine_tracts.py`);
   - licence-restricted neighbourhoods (optional);
   - synthetic calibration (only used by `build_demo_data.py`).
2. Optional data files:
   - `data/cities/<city>.geojson`: a real boundary instead of the bbox.
   - `data/ine/<city>.csv`: tract demographics. Set `ine_population_table` and
     `ine_income_table` in the registry, then run `python scripts/fetch_ine_tracts.py <city>`.
     This unlocks verdicts; see `data/ine/README.md`.
   - `data/rent/<city>.csv`: rent per neighbourhood; see `data/rent/README.md`.
3. Build the snapshot: `python scripts/pull_live_data.py <city>`.
4. Run `python scripts/validate_snapshots.py` and `make test`.
5. Open a PR with the snapshot committed under `data/sample_output/`.

The city appears in the app's dropdown automatically.

## Adding a cuisine

1. Add a `Cuisine(...)` entry to `src/cuisines.py`. It holds the exact OSM
   `cuisine=*` tokens, the Google Places type, the target income, the
   lunch share and the lunch/dinner tickets.
2. (Optional) add a weight profile to `CUISINE_PROFILES` in
   `src/scoring/weights.py`. Otherwise the default profile is used.
3. Rebuild snapshots so `cuisine_counts` includes it.

## Changing the model

`tests/golden/madrid_indian_medium_top10.json` pins the top-10 ranking on
the deterministic synthetic Madrid frame. If you change scoring or
economics on purpose, regenerate it and include the diff in your PR:

```bash
UPDATE_GOLDEN=1 python -m pytest tests/test_pipeline.py -k golden
```

## Code style

- Type hints everywhere.
- Each module gets a short docstring explaining what it does and why.
- Pure functions in `src/scoring/`, with no I/O, and keep the caller's index.
- Tests live in `tests/`. Use real H3 cells (see `tests/conftest.py`) when
  neighbour logic is involved.
- Error messages say what went wrong, why, and how to fix it.
