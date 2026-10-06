"""City boundary loading.

Boundaries are stored as GeoJSON FeatureCollections under data/cities/.
If a boundary file is missing we fall back to a simple bounding box around
the city centre (from `src/cities.py`) so the pipeline still runs
end-to-end.
"""
from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

from ..cities import CITIES, get_city

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "cities"


def _bbox_polygon(lat: float, lon: float, r: float) -> Polygon:
    return Polygon([
        (lon - r, lat - r),
        (lon + r, lat - r),
        (lon + r, lat + r),
        (lon - r, lat + r),
    ])


def boundary_source(city: str) -> str:
    """'geojson' if a real boundary file exists, else 'bbox'."""
    return "geojson" if (DATA_DIR / f"{city.strip().lower()}.geojson").exists() else "bbox"


def load_city_boundary(city: str) -> Polygon:
    """Return the city's boundary as a shapely Polygon (lon/lat, EPSG:4326)."""
    key = city.strip().lower()
    path = DATA_DIR / f"{key}.geojson"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            gj = json.load(f)
        geoms = []
        if gj.get("type") == "FeatureCollection":
            for feat in gj["features"]:
                geoms.append(shape(feat["geometry"]))
        elif gj.get("type") == "Feature":
            geoms.append(shape(gj["geometry"]))
        else:
            geoms.append(shape(gj))
        return unary_union(geoms)

    c = get_city(key)
    lat, lon = c.center
    return _bbox_polygon(lat, lon, c.radius_deg)


def city_center(city: str) -> tuple[float, float]:
    """Return (lat, lon) city centre, used for map initial view."""
    key = city.strip().lower()
    if key in CITIES:
        return CITIES[key].center
    poly = load_city_boundary(city)
    c = poly.centroid
    return (c.y, c.x)
