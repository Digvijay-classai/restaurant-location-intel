"""H3 hexagonal grid generation over a city boundary.

Resolution 8 hexes have an average edge length of ~460m and an area of
~0.74 km2, which is the sweet spot for urban zone analysis: small enough
to distinguish neighbourhoods, large enough to carry meaningful counts
of POIs and restaurants.
"""
from __future__ import annotations

from dataclasses import dataclass

import h3
from shapely.geometry import Polygon, mapping


DEFAULT_RES = 8


@dataclass(frozen=True)
class HexCell:
    h3_id: str
    center_lat: float
    center_lon: float
    boundary: list[tuple[float, float]]  # list of (lon, lat)

    def to_polygon(self) -> Polygon:
        return Polygon(self.boundary)


def _polyfill(polygon: Polygon, res: int) -> set[str]:
    """h3 v4 polyfill compatible with multiple API shapes."""
    gj = mapping(polygon)
    # h3-py v4
    if hasattr(h3, "polygon_to_cells"):
        from h3 import LatLngPoly

        if polygon.geom_type == "Polygon":
            coords = list(polygon.exterior.coords)
            holes = [list(r.coords) for r in polygon.interiors]
            # LatLngPoly expects (lat, lng)
            outer = [(y, x) for x, y in coords]
            hole_rings = [[(y, x) for x, y in h] for h in holes]
            poly = LatLngPoly(outer, *hole_rings)
            return set(h3.polygon_to_cells(poly, res))
        # MultiPolygon
        from h3 import LatLngMultiPoly, LatLngPoly as _P
        polys = []
        for part in polygon.geoms:
            outer = [(y, x) for x, y in part.exterior.coords]
            holes = [[(y, x) for x, y in r.coords] for r in part.interiors]
            polys.append(_P(outer, *holes))
        return set(h3.polygon_to_cells(LatLngMultiPoly(*polys), res))

    # Older h3 (should not happen with requirements.txt)
    return set(h3.polyfill(gj, res, geo_json_conformant=True))  # type: ignore[attr-defined]


def generate_hex_grid(boundary: Polygon, res: int = DEFAULT_RES) -> list[HexCell]:
    """Return every H3 cell whose centre falls inside the boundary polygon."""
    ids = _polyfill(boundary, res)
    cells: list[HexCell] = []
    for hid in ids:
        lat, lon = h3.cell_to_latlng(hid)
        boundary_latlng = h3.cell_to_boundary(hid)  # [(lat, lng), ...]
        boundary_lonlat = [(lng, lat) for lat, lng in boundary_latlng]
        cells.append(
            HexCell(
                h3_id=hid,
                center_lat=lat,
                center_lon=lon,
                boundary=boundary_lonlat,
            )
        )
    return cells


def hex_area_km2(res: int = DEFAULT_RES) -> float:
    """Average H3 cell area in km^2 for the given resolution."""
    return h3.average_hexagon_area(res, unit="km^2")
