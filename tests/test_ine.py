"""INE tract ingestion (parsing + catchment join), offline."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from src.data_sources import ine_api, ine_demographics


def _series(name, points):
    return {"Nombre": name, "Data": [{"Anyo": y, "Valor": v, "Secreto": s} for y, v, s in points]}


def test_parse_series_keeps_latest_non_empty_year():
    series = [
        _series("Barcelona sección 01003. Población. Dato base. ", [(2022, 2800.0, False), (2023, 2886.0, False)]),
        _series("Barcelona sección 01003. Porcentaje de población española. Dato base. ", [(2023, 55.4, False)]),
        _series("Barcelona sección 01003. Dato base. Renta neta media por hogar. ", [(2021, 40000.0, False), (2023, None, False)]),
        _series("Barcelona sección 01004. Dato base. Renta neta media por hogar. ", [(2023, 9.0, True)]),  # secret
        _series("Barcelona. Población. Dato base. ", [(2023, 1.6e6, False)]),  # municipality level: ignored
        _series("Hospitalet de Llobregat, L' sección 02001. Población. Dato base. ", [(2023, 1500.0, False)]),
    ]
    df = ine_api.parse_series(series, [ine_api.POPULATION, ine_api.PCT_SPANISH, ine_api.INCOME_HOUSEHOLD])
    got = {(r.municipality, r.code5, r.indicator): (r.value, r.year) for r in df.itertuples()}
    assert got == {
        ("Barcelona", "01003", ine_api.POPULATION): (2886.0, 2023),
        ("Barcelona", "01003", ine_api.PCT_SPANISH): (55.4, 2023),
        ("Barcelona", "01003", ine_api.INCOME_HOUSEHOLD): (40000.0, 2021),
        ("Hospitalet de Llobregat, L'", "02001", ine_api.POPULATION): (1500.0, 2023),
    }


def test_sections_frame_area_and_centroid():
    # ~0.01 deg square at 41.4N: 0.8348 km x 1.1057 km ~ 0.923 km2
    ring = [[2.17, 41.39], [2.18, 41.39], [2.18, 41.40], [2.17, 41.40], [2.17, 41.39]]
    feats = [{"attributes": {"cusec": "0801901003", "nmun": "Barcelona", "cdis": "01", "csec": "003"},
              "geometry": {"rings": [ring]}}]
    df = ine_api.sections_frame(feats)
    assert df.loc[0, "code5"] == "01003"
    assert df.loc[0, "area_km2"] == pytest.approx(0.923, rel=0.01)
    assert df.loc[0, "lat"] == pytest.approx(41.395) and df.loc[0, "lon"] == pytest.approx(2.175)


def test_build_tract_frame_joins_and_derives():
    sections = pd.DataFrame([{"tract_code": "0801901003", "municipality": "Barcelona", "code5": "01003",
                              "lat": 41.39, "lon": 2.17, "area_km2": 0.1}])
    stats = pd.DataFrame([
        {"municipality": "Barcelona", "code5": "01003", "indicator": ine_api.POPULATION, "value": 2000.0, "year": 2023},
        {"municipality": "Barcelona", "code5": "01003", "indicator": ine_api.PCT_SPANISH, "value": 80.0, "year": 2023},
        {"municipality": "Barcelona", "code5": "01003", "indicator": ine_api.INCOME_HOUSEHOLD, "value": 40000.0, "year": 2023},
        {"municipality": "Barcelona", "code5": "01003", "indicator": ine_api.INCOME_PERSON, "value": 16000.0, "year": 2023},
    ])
    out = ine_api.build_tract_frame(sections, stats).iloc[0]
    assert out["population_density"] == pytest.approx(20_000)
    assert out["pct_foreign"] == pytest.approx(20.0)
    assert out["income_year"] == 2023


def _tracts():
    # Two tracts within 1 km of (41.39, 2.17), one ~5 km away.
    return pd.DataFrame([
        {"lat": 41.390, "lon": 2.170, "population": 3000.0, "population_density": 30000.0,
         "income_household": 30000.0, "income_per_capita": 12000.0, "pct_foreign": 10.0},
        {"lat": 41.395, "lon": 2.172, "population": 1000.0, "population_density": 10000.0,
         "income_household": 50000.0, "income_per_capita": 20000.0, "pct_foreign": 30.0},
        {"lat": 41.435, "lon": 2.170, "population": 9000.0, "population_density": 9000.0,
         "income_household": 90000.0, "income_per_capita": 40000.0, "pct_foreign": 50.0},
    ])


def test_catchment_aggregates_population_weighted():
    z = ine_demographics.tract_demographics_for_hex(41.39, 2.17, "barcelona", _tracts())
    assert z.source == "ine_csv"
    assert z.population_density == pytest.approx(4000 / math.pi)
    assert z.income_household == pytest.approx((3000 * 30000 + 1000 * 50000) / 4000)
    assert z.pct_foreign == pytest.approx(15.0)


def test_catchment_falls_back_to_nearest_when_empty():
    z = ine_demographics.tract_demographics_for_hex(41.44, 2.17, "barcelona", _tracts(), radius_km=0.2)
    assert z.population_density == 9000.0 and z.income_household == 90000.0


def test_suppressed_income_uses_remaining_tracts():
    t = _tracts()
    t.loc[0, "income_household"] = float("nan")
    z = ine_demographics.tract_demographics_for_hex(41.39, 2.17, "barcelona", t)
    assert z.income_household == pytest.approx(50000.0)


def test_shipped_tract_csvs_cover_the_cities():
    for city, min_pop in (("barcelona", 1_500_000), ("madrid", 3_000_000), ("valladolid", 290_000)):
        df = ine_demographics.load_city_csv(city)
        assert df is not None and df["population"].sum() > min_pop
