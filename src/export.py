"""Exports of the scored hex table."""
from __future__ import annotations

import json
import math

import h3
import pandas as pd

NESTED_COLUMNS = ("cuisine_counts", "places_cuisine_counts")


def _clean(v):
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None  # inf/NaN are not valid JSON
    return v


def to_geojson(frame: pd.DataFrame) -> bytes:
    """Strict-JSON GeoJSON FeatureCollection (H3 polygons, inf/NaN -> null)."""
    features = []
    for _, row in frame.iterrows():
        coords = [[lng, lat] for lat, lng in h3.cell_to_boundary(row["h3_id"])]
        coords.append(coords[0])
        props = {k: _clean(v) for k, v in row.items() if k not in NESTED_COLUMNS}
        features.append({"type": "Feature",
                         "geometry": {"type": "Polygon", "coordinates": [coords]},
                         "properties": props})
    return json.dumps({"type": "FeatureCollection", "features": features},
                      allow_nan=False, default=str).encode("utf-8")
