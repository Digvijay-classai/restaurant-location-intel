"""Unit tests for the scoring engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.scoring.engine import (
    ScoreInputs,
    estimate_rent_eur_per_sqm,
    prepare_frame,
    ring_sum,
    score_hexes,
)
from src.scoring.weights import COMPONENTS, DEFAULT_WEIGHTS, normalise_weights, weights_for
from tests.conftest import CENTER, make_hex


def _inputs(cuisine="indian", budget="medium", weights=None) -> ScoreInputs:
    return ScoreInputs(cuisine, budget, hotel_beds_per_1000=48.0,
                       overnight_stays_per_capita=11.5, weights=weights)


# ---- weights ------------------------------------------------------------------

def test_weights_sum_to_one():
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9
    for cz in ["indian", "burger", "japanese", "italian", "unknown"]:
        w = weights_for(cz)
        assert set(w) == set(COMPONENTS)
        assert abs(sum(w.values()) - 1.0) < 1e-9


def test_normalise_weights_handles_zero_and_negative():
    eq = normalise_weights({c: 0.0 for c in COMPONENTS})
    assert all(abs(v - 1 / len(COMPONENTS)) < 1e-9 for v in eq.values())
    w = normalise_weights({"safety": -1.0, "foot_traffic": 2.0})
    assert w["safety"] == 0.0 and w["foot_traffic"] == 1.0


# ---- ring smoothing (regression: never ran under h3 v4) ---------------------

def test_ring_sum_uses_real_neighbours(ring_frame):
    df = ring_frame.assign(v=[0] + [10] * 6)
    out = ring_sum(df, "v", w=0.5)
    # centre: 0 + 0.5 * 60 = 30
    assert out.iloc[0] == pytest.approx(30.0)


def test_ring_sum_imputes_missing_edge_neighbours(ring_frame):
    """An edge hex with only some neighbours present is scaled up, not penalised."""
    df = ring_frame.assign(v=10)
    out = ring_sum(df, "v", w=0.5).iloc[1:]
    # every outer hex has 6 neighbours, of which 3 are in the frame (centre + 2)
    assert out.tolist() == pytest.approx([10 + 0.5 * 60] * 6)


def test_ring_sum_invalid_ids_get_no_neighbour_term():
    df = pd.DataFrame({"h3_id": ["a", "b"], "v": [3.0, 4.0]})
    assert ring_sum(df, "v").tolist() == [3.0, 4.0]


def test_competition_gap_sees_competitor_next_door(ring_frame):
    no_comp = score_hexes(ring_frame, _inputs())
    neighbour_comp = ring_frame.copy()
    neighbour_comp.loc[1, "same_cuisine"] = 4  # competitor in a NEIGHBOURING hex
    scored = score_hexes(neighbour_comp, _inputs())
    assert scored.loc[0, "competition_gap"] < no_comp.loc[0, "competition_gap"]


# ---- index safety and bad input (regression: NaN composites) ----------------

def test_score_hexes_preserves_non_range_index(grid_frame):
    sliced = grid_frame.iloc[5:15]
    scored = score_hexes(sliced, _inputs())
    assert scored.index.equals(sliced.index)
    assert scored["composite"].notna().all()


def test_nan_income_is_imputed_and_flagged(grid_frame):
    df = grid_frame.copy()
    df.loc[3, "income_household"] = np.nan
    scored = score_hexes(df, _inputs())
    assert scored["composite"].notna().all()
    assert scored.loc[3, "demographics_source"] == "imputed"


def test_missing_poi_columns_are_zero():
    row = make_hex(CENTER)
    for c in ("hotel", "tourism", "nightlife"):
        row.pop(c)
    scored = score_hexes(pd.DataFrame([row]), _inputs())
    assert scored.loc[0, "composite"] >= 0


def test_empty_frame_returns_empty():
    empty = pd.DataFrame(columns=["h3_id", "center_lat", "center_lon"])
    scored = score_hexes(empty, _inputs())
    assert scored.empty and "composite" in scored.columns


def test_missing_required_columns_raises():
    with pytest.raises(ValueError, match="h3_id"):
        prepare_frame(pd.DataFrame({"x": [1]}))


# ---- component behaviour ------------------------------------------------------

def test_composite_in_range_and_dense_core_beats_edge(grid_frame):
    scored = score_hexes(grid_frame, _inputs()).set_index("h3_id")
    assert scored["composite"].between(0, 100).all()
    edge = [h for h in scored.index if h != CENTER]
    assert scored.loc[CENTER, "foot_traffic"] > scored.loc[edge, "foot_traffic"].min()


def test_no_constant_offset_in_tourism(grid_frame):
    """Tourism is relative within the city: the least touristy hex scores 0."""
    scored = score_hexes(grid_frame, _inputs())
    assert scored["tourism_intensity"].min() == pytest.approx(0.0)
    assert scored["tourism_intensity"].max() == pytest.approx(1.0)


def test_bell_curve_penalises_saturation():
    from src.scoring.engine import _restaurant_ecosystem
    df = pd.DataFrame({"h3_id": ["a", "b", "c"], "restaurant": [0, 14, 45]})
    eco = _restaurant_ecosystem(df)
    assert eco[1] > eco[2] and eco[1] > eco[0]


def test_daypart_affects_foot_traffic(grid_frame):
    df = grid_frame.copy()
    df["office"] = range(len(df))          # day signal rises one way
    df["nightlife"] = range(len(df))[::-1]  # night signal rises the other way
    jap = score_hexes(df, _inputs("japanese"))["foot_traffic"]
    bur = score_hexes(df, _inputs("burger"))["foot_traffic"]
    assert not np.allclose(jap, bur)


def test_weights_override_changes_composite(grid_frame):
    """Regression: the sidebar weight sliders used to have no effect."""
    base = score_hexes(grid_frame, _inputs())
    only_safety = score_hexes(grid_frame, _inputs(weights={"safety": 1.0}))
    assert not np.allclose(base["composite"], only_safety["composite"])
    assert np.allclose(only_safety["composite"], (only_safety["safety"] * 100).round(1))


def test_confidence_rewards_measured_demographics(grid_frame):
    measured = score_hexes(grid_frame, _inputs())["confidence"]
    estimated = score_hexes(grid_frame.assign(demographics_source="city_median"), _inputs())["confidence"]
    assert (measured > estimated).all()
    assert measured.between(0, 1).all()


def test_rent_estimator_bounds():
    income = pd.Series([10_000, 40_000, 500_000])
    traffic = pd.Series([0, 50, 1_000])
    rent = estimate_rent_eur_per_sqm(income, traffic)
    assert (rent >= 10).all() and (rent <= 220).all()
    assert rent.iloc[2] == pytest.approx(22 + 55 * 1.5 + 48)  # clipped income factor


def test_rent_shrinkage_weights_by_listing_count():
    income = pd.Series([36_000.0, 36_000.0])
    traffic = pd.Series([10.0, 10.0])
    modelled = estimate_rent_eur_per_sqm(income, traffic)
    blended = estimate_rent_eur_per_sqm(income, traffic,
                                        listing_rents=pd.Series([100.0, 100.0]),
                                        listing_n=pd.Series([60, 4]))
    w60, w4 = 60 / 75, 4 / 19
    assert blended.iloc[0] == pytest.approx(w60 * 100 + (1 - w60) * modelled.iloc[0])
    assert blended.iloc[1] == pytest.approx(w4 * 100 + (1 - w4) * modelled.iloc[1])
