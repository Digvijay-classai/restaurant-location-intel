"""Neighbourhood name lookup from (lat, lon).

We want a human-readable name on every zone ("Eixample", "Chamberi"),
not a hex id. `src/cities.py` ships a minimal set of circular
neighbourhood centroids per city; a point is assigned to the nearest
centroid within its radius, otherwise "Outskirts". For higher precision,
swap these for the city's official district polygons (available from
opendata-ajuntament.barcelona.cat and datos.madrid.es).
"""
from __future__ import annotations

from ..cities import CITIES
from ..geo.distance import haversine_km

OUTSKIRTS = "Outskirts"


def neighbourhood_for(city: str, lat: float, lon: float) -> str:
    """Nearest-centroid neighbourhood lookup, 'Outskirts' if nothing within range."""
    c = CITIES.get(city.lower())
    if c is None:
        return OUTSKIRTS
    best = (OUTSKIRTS, 1e9)
    for name, hlat, hlon, radius in c.hoods:
        d = haversine_km(lat, lon, hlat, hlon)
        if d <= radius and d < best[1]:
            best = (name, d)
    return best[0]
