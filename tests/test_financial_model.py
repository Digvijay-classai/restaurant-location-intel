"""Unit tests for the unit-economics model, ranking and deal brief."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.scoring import financial_model as fm
from src.scoring.engine import ScoreInputs, score_hexes
from tests.conftest import make_hex


def _scored(rows: list[dict], cuisine="italian") -> pd.DataFrame:
    df = pd.DataFrame(rows)
    return score_hexes(df, ScoreInputs(cuisine, "medium", 32.0, 7.1))


def _econ(rows, cuisine="italian", city="madrid", size=150.0):
    return fm.compute(_scored(rows, cuisine), cuisine, city=city, size_sqm=size)


def _hexes(n: int, **kw) -> list[dict]:
    """n non-adjacent synthetic ids (no ring effects) with identical inputs."""
    return [make_hex(f"x{i}", **kw) for i in range(n)]


def test_revenue_non_increasing_in_competition():
    """Regression: revenue used to RISE with same-cuisine competitors."""
    rows = [make_hex(f"x{i}", same_cuisine=n) for i, n in enumerate([0, 1, 3, 8])]
    out = _econ(rows)
    rev = out["monthly_revenue_eur"].tolist()
    assert rev == sorted(rev, reverse=True)
    assert rev[0] > rev[-1]


def test_covers_capped_at_seat_capacity():
    out = _econ(_hexes(1, population_density=200_000.0))
    cap = fm.seats_for(150) * (fm.LUNCH_TURNS + fm.DINNER_TURNS) * fm.TRADING_DAYS_PER_MONTH * fm.MAX_PRACTICAL_FILL
    assert out.loc[0, "projected_covers_per_month"] == pytest.approx(round(cap))
    assert out.loc[0, "capacity_capped"]
    assert "demand exceeds seat capacity" in out.loc[0, "risk_flags"]


def test_zero_demand_gives_finite_breakeven():
    out = _econ(_hexes(1, population_density=0.0, hotel=0, tourism=0))
    assert out.loc[0, "monthly_revenue_eur"] == 0
    be = out.loc[0, "breakeven_covers_per_month"]
    assert math.isfinite(be) and be < 5_000  # was 12,264 with a 0 EUR ticket
    assert not out.loc[0, "concept_feasible"]


def test_labour_scales_with_covers():
    low = _econ(_hexes(1, population_density=4_000.0))
    high = _econ(_hexes(1, population_density=12_000.0))
    assert high.loc[0, "monthly_labour_eur"] > low.loc[0, "monthly_labour_eur"]
    share = high.loc[0, "monthly_labour_eur"] / high.loc[0, "monthly_revenue_eur"]
    assert 0.25 < share < 0.45


def test_size_scales_rent_capex_and_seats():
    small = _econ(_hexes(1), size=100)
    big = _econ(_hexes(1), size=300)
    assert big.loc[0, "seats"] == 3 * small.loc[0, "seats"]
    assert big.loc[0, "monthly_rent_eur"] == pytest.approx(3 * small.loc[0, "monthly_rent_eur"], rel=1e-3)
    assert big.loc[0, "capex_eur"] == pytest.approx(3 * small.loc[0, "capex_eur"], rel=1e-3)


def test_size_is_clamped():
    out = _econ(_hexes(1), size=5_000)
    assert out.loc[0, "size_sqm"] == fm.MAX_SIZE_SQM


def test_sensitivity_brackets_base_case():
    out = _econ(_hexes(3, population_density=11_000.0))
    assert (out["contribution_low_eur"] <= out["monthly_contribution_eur"]).all()
    assert (out["monthly_contribution_eur"] <= out["contribution_high_eur"]).all()


def test_composite_does_not_feed_revenue():
    """Economics and composite are independent (no 'tilt' double count)."""
    out = _econ(_hexes(2))
    tweaked = out.copy()
    tweaked["composite"] = [10.0, 90.0]
    again = fm.compute(tweaked.drop(columns=["risk_flags"]), "italian", city="madrid")
    assert again["monthly_revenue_eur"].tolist() == out["monthly_revenue_eur"].tolist()


def test_licence_flag_is_city_scoped():
    """Regression: Valladolid 'Centro' used to get Madrid's BIC flag."""
    row = [make_hex("x0", neighbourhood="Centro")]
    madrid = _econ(row, city="madrid")
    valladolid = _econ(row, city="valladolid")
    flag = "licence/BIC proximity — verify sub-barrio"
    assert flag in madrid.loc[0, "risk_flags"]
    assert flag not in valladolid.loc[0, "risk_flags"]


def test_empty_frame():
    assert fm.compute(pd.DataFrame(), "italian").empty


# ---- ranking ---------------------------------------------------------------

def _rank_input() -> pd.DataFrame:
    return pd.DataFrame({
        "neighbourhood":            ["A", "B", "C", "Outskirts", "D"],
        "concept_feasible":         [True, True, True, True, False],
        "payback_months":           [40.0, 20.0, math.inf, 10.0, math.inf],
        "monthly_contribution_eur": [5_000, 9_000, 1_500, 20_000, -3_000],
        "composite":                [50.0, 40.0, 80.0, 99.0, 90.0],
    }, index=[10, 11, 12, 13, 14])


def test_rank_zones_is_economics_first():
    ranked = fm.rank_zones(_rank_input())
    order = ranked.sort_values("rank")["neighbourhood"].tolist()
    # viable by payback (B 20 < A 40), then feasible-no-payback, then below
    # break-even, then Outskirts last regardless of score.
    assert order == ["B", "A", "C", "D", "Outskirts"]
    assert ranked.index.tolist() == [10, 11, 12, 13, 14]
    assert sorted(ranked["rank"]) == [1, 2, 3, 4, 5]


def test_rank_zones_empty():
    empty = _rank_input().iloc[0:0]
    assert fm.rank_zones(empty).empty


# ---- deal brief ------------------------------------------------------------

def _brief_row(**kw) -> pd.Series:
    out = _econ([make_hex("x0", population_density=14_000.0, **kw)])
    return out.iloc[0]


def test_brief_without_verdict_when_data_not_real():
    text = fm.deal_brief(_brief_row(), "italian", "madrid", verdicts_allowed=False)
    assert "Verdict" not in text and "No verdict" in text


def test_brief_with_verdict_and_ranges():
    text = fm.deal_brief(_brief_row(), "italian", "madrid", verdicts_allowed=True)
    assert "Verdict:" in text
    assert "Downside case" in text and "Upside case" in text
    assert "€" in text


def test_brief_cautions_when_capacity_capped():
    row = _econ(_hexes(1, population_density=200_000.0)).iloc[0]
    assert row["capacity_capped"] and row["concept_feasible"]
    assert "exceeds seat capacity" in fm.deal_brief(row, "italian", "madrid", verdicts_allowed=True)


def test_brief_is_nan_safe():
    row = _brief_row().copy()
    for col in ("monthly_revenue_eur", "projected_covers_per_month", "payback_months", "composite"):
        row[col] = np.nan
    text = fm.deal_brief(row, "italian", "madrid")
    assert "No payback within 10 yrs" in text


def test_brief_does_not_repeat_risk_flags():
    row = _brief_row(same_cuisine=6)
    assert row["risk_flags"]
    assert "Risk flags" not in fm.deal_brief(row, "italian", "madrid")
