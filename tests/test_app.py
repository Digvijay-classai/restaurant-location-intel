"""End-to-end UI tests with Streamlit's AppTest (no browser, no network)."""
from __future__ import annotations

import json
import re

import pytest
from streamlit.testing.v1 import AppTest

APP = "app.py"


@pytest.fixture
def app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _header(at: AppTest) -> str:
    return next(m.value for m in at.markdown if m.value.startswith("<h2"))


def _anchor(at: AppTest) -> str:
    return next(m.value for m in at.markdown if "class='anchor'" in m.value)


def test_provenance_banner_matches_snapshot_and_gates_verdicts(app):
    from src.pipeline import is_synthetic, load_snapshot, verdicts_allowed
    meta = load_snapshot("barcelona").meta
    if is_synthetic(meta):
        assert any("SYNTHETIC DEMO DATA" in w.value for w in app.warning)
    elif not verdicts_allowed(meta):
        assert any("estimated demographics" in i.value for i in app.info)
    else:
        assert any("Live data" in s.value for s in app.success)
    briefs = " ".join(m.value for m in app.markdown)
    if not verdicts_allowed(meta):
        assert "Verdict:" not in briefs


def test_synthetic_snapshot_shows_banner(tmp_path, monkeypatch):
    """With a synthetic snapshot the app must say so and give no verdicts."""
    at = _synthetic_app(tmp_path, monkeypatch)
    assert not at.exception
    assert any("SYNTHETIC DEMO DATA" in w.value for w in at.warning)
    assert "Verdict:" not in " ".join(m.value for m in at.markdown)
    import streamlit as st
    st.cache_data.clear()


def test_header_follows_city_change_without_extra_click(app):
    """Regression: changing city kept the old city's data under the new title."""
    app.sidebar.selectbox[0].set_value("madrid").run()
    assert not app.exception
    assert "Madrid" in _header(app)
    hoods = re.search(r"class='hood'>(.*?)</p>", _anchor(app)).group(1)
    from src.cities import CITIES
    assert hoods in {h[0] for h in CITIES["madrid"].hoods}


def test_weight_slider_changes_scores(app):
    """Regression: weight sliders had no effect."""
    before = _anchor(app)
    sliders = [s for s in app.sidebar.slider if s.label != "Minimum confidence"]
    for s in sliders:
        s.set_value(0.0)
    next(s for s in sliders if s.label == "Safety").set_value(1.0)
    app.run()
    assert not app.exception
    assert _anchor(app) != before


def test_size_input_changes_economics(app):
    before = _anchor(app)
    app.sidebar.number_input[0].set_value(300).run()
    assert not app.exception
    assert "300 sqm" in _header(app) and _anchor(app) != before


def _synthetic_app(tmp_path, monkeypatch) -> AppTest:
    """App running on synthetic snapshots (confidence never exceeds 0.8)."""
    import streamlit as st
    from scripts.build_demo_data import generate_city, synthetic_meta
    from src import pipeline
    for city in ("barcelona", "madrid", "valladolid"):
        pipeline.write_snapshot(city, generate_city(city), synthetic_meta(city),
                                tmp_path / f"{city}_demo.json")
    monkeypatch.setattr(pipeline, "SAMPLE_DIR", tmp_path)
    st.cache_data.clear()  # the cache is process-wide; don't reuse other tests' results
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    return at


def test_confidence_filter_empty_state(tmp_path, monkeypatch):
    at = _synthetic_app(tmp_path, monkeypatch)
    next(s for s in at.sidebar.slider if s.label == "Minimum confidence").set_value(1.0).run()
    assert not at.exception
    assert any("confidence filter" in w.value for w in at.warning)
    import streamlit as st
    st.cache_data.clear()


def test_geojson_export_is_strict_json():
    """Regression: payback=inf produced `Infinity`, which is invalid JSON."""
    from src.export import to_geojson
    from src.pipeline import run_pipeline
    df = run_pipeline("valladolid", "thai", "medium")
    assert (df["payback_months"] == float("inf")).any()
    gj = json.loads(to_geojson(df), parse_constant=lambda c: pytest.fail(f"non-strict JSON: {c}"))
    assert len(gj["features"]) == len(df)


def test_every_city_and_cuisine_renders():
    from src.cities import CITY_KEYS
    from src.cuisines import CUISINE_KEYS
    at = AppTest.from_file(APP, default_timeout=90).run()
    for city in CITY_KEYS:
        at.sidebar.selectbox[0].set_value(city)
        for cz in CUISINE_KEYS:
            at.sidebar.selectbox[1].set_value(cz).run()
            assert not at.exception, (city, cz, [e.message for e in at.exception])


def test_places_snapshot_hides_map_and_credits_google(tmp_path, monkeypatch):
    """Google terms: Places content must not be shown on a non-Google map."""
    import streamlit as st
    from scripts.build_demo_data import generate_city, synthetic_meta
    from src import pipeline
    for city in ("barcelona", "madrid", "valladolid"):
        df = generate_city(city)
        df["places_cuisine_counts"] = df["cuisine_counts"]
        df["places_restaurant"] = df["restaurant"]
        meta = synthetic_meta(city)
        meta["sources"]["competitors"] = pipeline.GOOGLE_PLACES
        pipeline.write_snapshot(city, df, meta, tmp_path / f"{city}_demo.json")
    monkeypatch.setattr(pipeline, "SAMPLE_DIR", tmp_path)
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=90).run()
    st.cache_data.clear()
    assert not at.exception
    assert any("Map hidden" in i.value for i in at.info)
    assert any("Powered by Google" in c.value for c in at.caption)


def test_footer_has_attribution_and_disclaimer(app):
    captions = " ".join(c.value for c in app.caption)
    for needle in ("OpenStreetMap", "INE", "Ministerio del Interior", "not financial", "Privacy"):
        assert needle in captions
