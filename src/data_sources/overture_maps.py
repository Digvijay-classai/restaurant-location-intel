"""OpenStreetMap POI adapter (via the Overpass API).

Despite the module name (kept for import compatibility), this queries
OpenStreetMap through Overpass, not Overture Maps.

We issue ONE query per city bounding box, pulling all POI types we care
about in a single pass, then spatially join the points to H3 cells. Nodes,
ways and relations are all included (`nwr`): many restaurants and shops
are mapped as building outlines (ways), and Overpass returns their centre.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import h3
import requests
from shapely.geometry import Polygon

from ..cuisines import CUISINES, matches

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MIRROR_HINT = (
    "Set OVERPASS_URL to a mirror (e.g. https://overpass.kumi.systems/api/interpreter) "
    "in .env, or retry later."
)

# overpass-api.de rejects the default python-requests User-Agent (HTTP 406).
USER_AGENT = "restaurant-location-intel/0.3 (+https://github.com/; site-selection research)"

POI_CATEGORIES = {
    "restaurant":  '["amenity"="restaurant"]',
    "shop":        '["shop"]',
    "transit":     '["public_transport"="station"]',
    "bus_stop":    '["highway"="bus_stop"]',
    "tourism":     '["tourism"~"^(attraction|museum|gallery|viewpoint|artwork)$"]',
    "hotel":       '["tourism"~"^(hotel|hostel|guest_house)$"]',
    "office":      '["office"]',
    "nightlife":   '["amenity"~"^(bar|pub|nightclub)$"]',
}


class OverpassError(RuntimeError):
    """Overpass could not be reached or returned an unusable response."""


@dataclass
class POI:
    lat: float
    lon: float
    category: str
    tags: dict[str, str]


def overpass_url() -> str:
    return os.getenv("OVERPASS_URL") or DEFAULT_OVERPASS_URL


def _bbox_of(polygon: Polygon) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) for Overpass bbox syntax."""
    minx, miny, maxx, maxy = polygon.bounds
    return (miny, minx, maxy, maxx)


def _build_query(bbox: tuple[float, float, float, float], timeout_s: int = 180) -> str:
    south, west, north, east = bbox
    bbox_str = f"({south},{west},{north},{east})"
    body = "\n  ".join(f"nwr{filt}{bbox_str};" for filt in POI_CATEGORIES.values())
    return f"[out:json][timeout:{timeout_s}];\n(\n  {body}\n);\nout tags center;"


def _cache_key(city: str) -> Path:
    return CACHE_DIR / f"osm_{city.lower()}.json"


def _download(query: str, attempts: int = 3) -> dict:
    url = overpass_url()
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = requests.post(url, data={"data": query}, timeout=240,
                                 headers={"User-Agent": USER_AGENT})
            if resp.status_code in (429, 504):
                raise OverpassError(f"Overpass returned HTTP {resp.status_code} (busy)")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError, OverpassError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(10 * (attempt + 1))
    raise OverpassError(
        f"Could not fetch POIs from {url} after {attempts} attempts: {last}. {MIRROR_HINT}"
    ) from last


def fetch_pois(city: str, boundary: Polygon, use_cache: bool = True) -> list[POI]:
    """Return every POI in the city bbox, categorized.

    Raw responses are cached under data/cache/. A corrupt cache file is
    discarded and re-downloaded.
    """
    cache_path = _cache_key(city)
    raw: dict | None = None
    if use_cache and cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw = None
    if raw is None:
        raw = _download(_build_query(_bbox_of(boundary)))
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(raw, f)
    return parse_elements(raw.get("elements", []))


def parse_elements(elements: Iterable[dict]) -> list[POI]:
    """Convert Overpass elements (nodes, or ways/relations with `center`) to POIs."""
    pois: list[POI] = []
    for el in elements:
        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {}) or {}
        cat = classify(tags)
        if cat is None:
            continue
        pois.append(POI(lat=float(lat), lon=float(lon), category=cat, tags=tags))
    return pois


def classify(tags: dict[str, str]) -> str | None:
    if tags.get("amenity") == "restaurant":
        return "restaurant"
    if "shop" in tags:
        return "shop"
    if tags.get("public_transport") == "station":
        return "transit"
    if tags.get("highway") == "bus_stop":
        return "bus_stop"
    tour = tags.get("tourism")
    if tour in {"hotel", "hostel", "guest_house"}:
        return "hotel"
    if tour in {"attraction", "museum", "gallery", "viewpoint", "artwork"}:
        return "tourism"
    if "office" in tags:
        return "office"
    if tags.get("amenity") in {"bar", "pub", "nightclub"}:
        return "nightlife"
    return None


def pois_to_hex_counts(pois: Iterable[POI], res: int = 8) -> dict[str, dict]:
    """Aggregate POIs by H3 cell.

    Returns {hex_id: {category: count, ..., "cuisine_counts": {cuisine: n}}}.
    A restaurant tagged "pizza;burger" counts towards both cuisines.
    """
    buckets: dict[str, dict] = {}
    for p in pois:
        hid = h3.latlng_to_cell(p.lat, p.lon, res)
        d = buckets.setdefault(hid, {**{k: 0 for k in POI_CATEGORIES},
                                     "cuisine_counts": {k: 0 for k in CUISINES}})
        d[p.category] += 1
        if p.category == "restaurant":
            tag = p.tags.get("cuisine")
            for cz in CUISINES:
                if matches(cz, tag):
                    d["cuisine_counts"][cz] += 1
    return buckets
