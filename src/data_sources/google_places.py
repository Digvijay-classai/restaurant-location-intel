"""Google Places API (New) adapter with SQLite caching.

Optional enhancement used only by the snapshot refresh
(`scripts/pull_live_data.py --places`), never on page load: a full city
refresh costs ~1 call per hex per cuisine plus one for all restaurants.

Counts come from `places:searchNearby` with `includedTypes` set to the
cuisine's Places type (e.g. `italian_restaurant`). The API returns at most
20 places per call, so counts saturate at 20; `count_restaurants` reports
that via `PLACES_MAX_RESULTS`.
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import requests

from ..cuisines import CUISINES

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
DB_PATH = CACHE_DIR / "places.sqlite"

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_MAX_RESULTS = 20


class PlacesError(RuntimeError):
    """Google Places request failed (bad key, quota, network)."""


def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS places_cache (
            hex_id TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            radius REAL NOT NULL,
            count INTEGER NOT NULL,
            fetched_at REAL NOT NULL,
            PRIMARY KEY (hex_id, cuisine, radius)
        )"""
    )
    return con


def _cache_get(hex_id: str, cuisine: str, radius: float) -> int | None:
    with _connect() as con:
        row = con.execute(
            "SELECT count FROM places_cache WHERE hex_id=? AND cuisine=? AND radius=?",
            (hex_id, cuisine, radius),
        ).fetchone()
    return row[0] if row else None


def _cache_put(hex_id: str, cuisine: str, radius: float, count: int) -> None:
    with _connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO places_cache VALUES (?,?,?,?,?)",
            (hex_id, cuisine, radius, count, time.time()),
        )


def api_key_present() -> bool:
    return bool(os.getenv("GOOGLE_PLACES_API_KEY"))


def count_restaurants(
    lat: float,
    lon: float,
    hex_id: str,
    cuisine: str | None = None,
    radius_m: float = 500.0,
) -> int:
    """Return number of restaurants near (lat, lon), optionally one cuisine.

    cuisine=None means all restaurants. Uses the SQLite cache; the API is
    called only on a cache miss. Raises PlacesError with the cause and fix.
    """
    key_cuisine = cuisine or "__all__"
    cached = _cache_get(hex_id, key_cuisine, radius_m)
    if cached is not None:
        return cached

    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise PlacesError(
            "GOOGLE_PLACES_API_KEY is not set. Add it to .env "
            "(see .env.example) or run without --places."
        )
    if cuisine is not None and cuisine not in CUISINES:
        raise PlacesError(f"Unknown cuisine {cuisine!r}; known: {', '.join(CUISINES)}")

    included = [CUISINES[cuisine].places_type] if cuisine else ["restaurant"]
    body: dict[str, Any] = {
        "includedTypes": included,
        "maxResultCount": PLACES_MAX_RESULTS,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": radius_m}
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id",
    }
    try:
        resp = requests.post(PLACES_URL, json=body, headers=headers, timeout=30)
    except requests.RequestException as exc:
        raise PlacesError(f"Network error calling Google Places: {exc}") from exc
    if resp.status_code in (401, 403):
        raise PlacesError(
            f"Google Places rejected the key (HTTP {resp.status_code}). Check the key "
            "and that 'Places API (New)' is enabled for the project."
        )
    if resp.status_code == 429:
        raise PlacesError("Google Places quota exceeded (HTTP 429). Retry later; cached hexes are kept.")
    if resp.status_code != 200:
        raise PlacesError(f"Google Places returned HTTP {resp.status_code}: {resp.text[:200]}")
    count = len(resp.json().get("places", []))
    _cache_put(hex_id, key_cuisine, radius_m, count)
    return count
