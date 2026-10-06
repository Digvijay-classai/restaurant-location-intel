"""Pipeline, snapshot and script tests (no network)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src import pipeline
from src.cities import CITY_KEYS
from src.data_sources import overture_maps

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden" / "madrid_indian_medium_top10.json"


def _synthetic(city="madrid"):
    from scripts.build_demo_data import generate_city, synthetic_meta
    return generate_city(city), synthetic_meta(city)


# ---- snapshots ----------------------------------------------------------------

@pytest.mark.parametrize("city", CITY_KEYS)
def test_committed_snapshots_are_valid(city):
    payload = json.loads(pipeline.precomputed_path(city).read_text(encoding="utf-8"))
    assert pipeline.validate_snapshot(payload) == []


def test_validate_snapshot_reports_problems():
    assert "missing 'meta' block (schema v2)" in pipeline.validate_snapshot({"hexes": [{}]})
    assert any("non-empty" in p for p in pipeline.validate_snapshot({"meta": {}, "hexes": []}))


def test_legacy_snapshot_meta_is_marked_synthetic():
    meta = pipeline._legacy_meta({"generated_with": "scripts/build_demo_data.py"})
    assert pipeline.is_synthetic(meta) and not pipeline.verdicts_allowed(meta)


def test_corrupt_snapshot_error_says_how_to_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "SAMPLE_DIR", tmp_path)
    (tmp_path / "madrid_demo.json").write_text("{oops")
    with pytest.raises(ValueError, match="pull_live_data.py madrid"):
        pipeline.load_snapshot("madrid")


def test_write_snapshot_refuses_invalid(tmp_path):
    with pytest.raises(ValueError, match="invalid snapshot"):
        pipeline.write_snapshot("madrid", pd.DataFrame([{"h3_id": "x"}]), {"city": "madrid"},
                                tmp_path / "s.json")


# ---- synthetic generator --------------------------------------------------------

def test_synthetic_generator_is_deterministic_across_processes():
    """Regression: seeded with hash(city), which Python salts per process."""
    code = ("from scripts.build_demo_data import generate_city;"
            "print(generate_city('valladolid')['income_household'].sum())")
    outs = set()
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outs.add(subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                                capture_output=True, text=True, check=True).stdout)
    assert len(outs) == 1


def test_build_demo_data_keeps_live_snapshots(tmp_path, monkeypatch):
    from scripts import build_demo_data
    monkeypatch.setattr(pipeline, "SAMPLE_DIR", tmp_path)
    df, meta = _synthetic("valladolid")
    live_meta = {**meta, "sources": {**meta["sources"], "pois": pipeline.LIVE_OSM}}
    pipeline.write_snapshot("valladolid", df, live_meta)
    before = (tmp_path / "valladolid_demo.json").read_bytes()

    build_demo_data.main(["--city", "valladolid"])
    assert (tmp_path / "valladolid_demo.json").read_bytes() == before

    build_demo_data.main(["--city", "valladolid", "--force"])
    assert pipeline.existing_snapshot_source("valladolid") == pipeline.SYNTHETIC


# ---- live builder with mocked Overpass --------------------------------------------

def test_build_base_frame_offline(monkeypatch, tmp_path):
    from src.data_sources import ine_demographics
    monkeypatch.setattr(ine_demographics, "DATA_DIR", tmp_path)  # no tract CSV
    monkeypatch.setattr(overture_maps, "_download", lambda q: {"elements": [
        {"type": "node", "lat": 41.6523, "lon": -4.7245,
         "tags": {"amenity": "restaurant", "cuisine": "thai"}},
        {"type": "way", "center": {"lat": 41.6523, "lon": -4.7245}, "tags": {"shop": "books"}},
    ]})
    monkeypatch.setattr(overture_maps, "CACHE_DIR", Path(os.environ.get("TMPDIR", "/tmp")) / "rli-test-cache")
    res = pipeline.build_base_frame("valladolid", use_cache=False)
    assert res.meta["sources"]["pois"] == pipeline.LIVE_OSM
    assert res.meta["sources"]["demographics"] == "city_median"
    assert pipeline.validate_snapshot({"meta": res.meta,
                                       "hexes": json.loads(res.df.to_json(orient="records"))}) == []
    assert res.df["restaurant"].sum() == 1 and res.df["shop"].sum() == 1
    assert sum(d["thai"] for d in res.df["cuisine_counts"]) == 1
    assert not pipeline.verdicts_allowed(res.meta)  # city-median demographics


def test_build_base_frame_uses_tract_csv(monkeypatch):
    monkeypatch.setattr(overture_maps, "_download", lambda q: {"elements": []})
    monkeypatch.setattr(overture_maps, "CACHE_DIR", Path(os.environ.get("TMPDIR", "/tmp")) / "rli-test-cache")
    res = pipeline.build_base_frame("valladolid", use_cache=False)
    assert res.meta["sources"]["demographics"] == "ine_csv"
    assert res.df["population_density"].nunique() > 10  # varies by hex, not a city constant


def test_verdicts_require_live_pois_and_ine_demographics():
    ok = {"sources": {"pois": pipeline.LIVE_OSM, "demographics": "ine_csv"}}
    assert pipeline.verdicts_allowed(ok)
    assert not pipeline.verdicts_allowed({"sources": {"pois": "synthetic", "demographics": "ine_csv"}})


# ---- enrichment ------------------------------------------------------------------

def test_places_counts_override_osm_competitors():
    df, meta = _synthetic("valladolid")
    df = df.head(3).copy()
    df["places_cuisine_counts"] = [{"thai": 7}] * 3
    df["places_restaurant"] = [20] * 3
    meta = {**meta, "sources": {**meta["sources"], "competitors": pipeline.GOOGLE_PLACES}}
    out = pipeline._enrich(df, "valladolid", "thai", meta)
    assert (out["same_cuisine"] == 7).all() and (out["restaurant"] == 20).all()
    assert (out["competitor_source"] == pipeline.GOOGLE_PLACES).all()


def test_rent_join_uses_normalised_names():
    df, meta = _synthetic("barcelona")
    out = pipeline._enrich(df, "barcelona", "indian", meta)
    named = out[out["neighbourhood"] == "Sarria-Sant Gervasi"]
    assert not named.empty and named["listing_rent"].notna().all()


# ---- end to end -------------------------------------------------------------------

@pytest.mark.parametrize("city", CITY_KEYS)
def test_run_pipeline_end_to_end(city):
    res = pipeline.run_pipeline_with_meta(city, "italian", "medium")
    df = res.df
    assert len(df) > 50 and df["composite"].between(0, 100).all()
    assert sorted(df["rank"]) == list(range(1, len(df) + 1))
    assert df["composite"].notna().all()
    assert res.meta["rent"] == "seeded_cw_cbre_2024"


def test_golden_ranking_madrid_indian_medium():
    """Model changes must show up as a reviewed diff of this file.

    Regenerate: UPDATE_GOLDEN=1 pytest tests/test_pipeline.py -k golden
    """
    df, meta = _synthetic("madrid")
    scored = pipeline.score_frame(df, meta, "madrid", "indian", "medium")
    top = scored.sort_values("rank").head(10)
    got = [{"rank": int(r["rank"]), "h3_id": r["h3_id"], "tier": int(r["rank_tier"]),
            "composite": float(r["composite"])} for _, r in top.iterrows()]
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1) + "\n")
    assert got == json.loads(GOLDEN.read_text())


# ---- scripts run as documented ------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    ["scripts/pull_live_data.py", "--help"],
    ["scripts/import_rent_listings.py", "--help"],
    ["scripts/fetch_ine_tracts.py", "--help"],
    ["scripts/build_demo_data.py", "--help"],
    ["-m", "scripts.pull_live_data", "--help"],
])
def test_scripts_start(cmd):
    """Regression: these crashed with ModuleNotFoundError: No module named 'src'."""
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "usage:" in r.stdout


def test_validate_snapshots_script_passes():
    r = subprocess.run([sys.executable, "scripts/validate_snapshots.py"], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_validate_snapshots_rejects_google_places(tmp_path, monkeypatch):
    from scripts import validate_snapshots
    df, meta = _synthetic("valladolid")
    meta["sources"]["competitors"] = pipeline.GOOGLE_PLACES
    for city in CITY_KEYS:
        pipeline.write_snapshot(city, df, meta, tmp_path / f"{city}_demo.json")
    monkeypatch.setattr(validate_snapshots, "precomputed_path", lambda c: tmp_path / f"{c}_demo.json")
    assert validate_snapshots.main() == 1
