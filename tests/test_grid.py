"""Grid generation smoke test."""
from shapely.geometry import Polygon

from src.geo.grid import generate_hex_grid, hex_area_km2


def test_generate_small_grid():
    # ~5km square around central Madrid.
    r = 0.025
    poly = Polygon([(-3.72 - r, 40.42 - r),
                    (-3.72 + r, 40.42 - r),
                    (-3.72 + r, 40.42 + r),
                    (-3.72 - r, 40.42 + r)])
    cells = generate_hex_grid(poly, res=8)
    assert len(cells) > 10
    assert hex_area_km2(8) > 0
