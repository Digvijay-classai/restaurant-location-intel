"""Shared fixtures. Uses REAL H3 cells so ring smoothing is exercised.

(The original suite used fake ids "a"/"b"/"c", which silently skipped the
neighbour code path and hid a bug where smoothing never ran.)
"""
from __future__ import annotations

import h3
import pandas as pd
import pytest

CENTER = h3.latlng_to_cell(41.3874, 2.1686, 8)  # central Barcelona


def make_hex(hid: str, **overrides) -> dict:
    """A plausible hex row. Non-H3 ids (e.g. "x0") get no neighbours when scored."""
    lat, lon = h3.cell_to_latlng(hid) if h3.is_valid_cell(hid) else (41.39, 2.17)
    row = {
        "h3_id": hid, "center_lat": lat, "center_lon": lon,
        "restaurant": 5, "shop": 20, "transit": 1, "bus_stop": 3,
        "tourism": 2, "hotel": 1, "office": 5, "nightlife": 2,
        "same_cuisine": 0, "income_household": 36_000.0,
        "income_per_capita": 15_000.0, "pct_foreign": 20.0,
        "population_density": 12_000.0, "demographics_source": "ine_csv",
        "crime_per_1000": 50.0, "neighbourhood": "Eixample",
    }
    row.update(overrides)
    return row


@pytest.fixture
def ring_frame() -> pd.DataFrame:
    """Centre hex + its 6 neighbours (7 rows)."""
    ring = [n for n in h3.grid_disk(CENTER, 1) if n != CENTER]
    return pd.DataFrame([make_hex(CENTER)] + [make_hex(n) for n in sorted(ring)])


@pytest.fixture
def grid_frame() -> pd.DataFrame:
    """Hex + 2 rings (19 rows) with a dense core and a sparse edge."""
    rows = []
    for hid in sorted(h3.grid_disk(CENTER, 2)):
        d = h3.grid_distance(CENTER, hid)
        rows.append(make_hex(
            hid,
            restaurant=[20, 10, 2][d], shop=[60, 30, 5][d], office=[20, 8, 1][d],
            hotel=[6, 2, 0][d], tourism=[8, 3, 0][d], nightlife=[10, 4, 0][d],
            transit=[3, 1, 0][d], same_cuisine=[3, 1, 0][d],
            income_household=[42_000, 36_000, 26_000][d],
        ))
    return pd.DataFrame(rows)
