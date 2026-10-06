"""Fetch census-tract (seccion censal) demographics from INE's public APIs.

Two free, keyless INE services, joined on (municipality name, district +
section code):

1. **Section polygons**: INE's ArcGIS FeatureServer for the Atlas de
   Distribucion de Renta de los Hogares (layer "Nivel: Secciones
   censales"). Queried by the city's bounding box, so neighbouring
   municipalities inside the box (L'Hospitalet, Badalona...) are included.
2. **Section statistics**: INE Tempus JSON API (`servicios.ine.es/wstempus`),
   ADRH tables per province:
   - "Indicadores demograficos": Poblacion, Porcentaje de poblacion espanola
   - "Indicadores de renta media y mediana": Renta neta media por hogar /
     por persona

For each series we keep the latest non-empty year and record it.
Values INE suppresses for statistical secrecy come back empty and stay NaN.

Used by `scripts/fetch_ine_tracts.py`. Network-only; parsing is split into
pure functions so it can be tested offline.
"""
from __future__ import annotations

import math
import re
import time
from collections.abc import Iterable

import pandas as pd
import requests
from shapely.geometry import Polygon
from shapely.ops import unary_union

FEATURE_SERVER = ("https://www.ine.es/servergis/rest/services/Hosted/"
                  "Renta_media_por_hogar/FeatureServer/2/query")
TEMPUS = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{table}?nult={n}"
USER_AGENT = "restaurant-location-intel/0.3 (site-selection research)"

# Margin (degrees) added around the city bbox so hexes on the edge still see
# residents across the line (~1.3 km).
BBOX_MARGIN_DEG = 0.012

POPULATION = "Población"
PCT_SPANISH = "Porcentaje de población española"
INCOME_HOUSEHOLD = "Renta neta media por hogar"
INCOME_PERSON = "Renta neta media por persona"

_SERIES_RE = re.compile(r"^(?P<muni>.+?) sección (?P<code>\d{5})\. (?P<rest>.*)$")


class INEError(RuntimeError):
    """An INE service could not be reached or returned something unusable."""


def _get_json(url: str, params: dict | None = None, attempts: int = 3, timeout: int = 300):
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(5 * (attempt + 1))
    raise INEError(f"INE request failed after {attempts} attempts ({url}): {last}") from last


# ---- section polygons -----------------------------------------------------------


def fetch_section_features(center: tuple[float, float], radius_deg: float) -> list[dict]:
    """Raw ArcGIS features (attributes + WGS84 rings) for sections in the bbox."""
    lat, lon = center
    r = radius_deg + BBOX_MARGIN_DEG
    base = {
        "geometry": f"{lon - r},{lat - r},{lon + r},{lat + r}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "cusec,nmun,cdis,csec",
        "returnGeometry": "true",
        "maxAllowableOffset": "0.00005",   # ~5 m simplification, keeps payloads small
        "orderByFields": "cusec",
        "resultRecordCount": 1000,
        "f": "json",
    }
    feats: list[dict] = []
    offset = 0
    while True:
        page = _get_json(FEATURE_SERVER, {**base, "resultOffset": offset})
        if "error" in page:
            raise INEError(f"INE FeatureServer error: {page['error']}")
        batch = page.get("features", [])
        feats.extend(batch)
        if not page.get("exceededTransferLimit") or not batch:
            return feats
        offset += len(batch)


def _area_km2(poly: Polygon) -> float:
    """Area of a lon/lat polygon via a local equirectangular projection."""
    lat0 = math.radians(poly.centroid.y)
    kx, ky = 111.320 * math.cos(lat0), 110.574
    xs, ys = poly.exterior.coords.xy
    proj = Polygon([(x * kx, y * ky) for x, y in zip(xs, ys)],
                   [[(x * kx, y * ky) for x, y in zip(*r.coords.xy)] for r in poly.interiors])
    return proj.area


def sections_frame(features: Iterable[dict]) -> pd.DataFrame:
    """[tract_code, municipality, code5, lat, lon, area_km2] from ArcGIS features."""
    rows = []
    for f in features:
        a, g = f["attributes"], f.get("geometry") or {}
        rings = g.get("rings") or []
        if not rings:
            continue
        # ArcGIS rings: outer rings clockwise, holes counter-clockwise. Treat
        # each ring as a polygon and union; holes are rare at section level.
        parts = [Polygon(r) for r in rings if len(r) >= 4]
        geom = unary_union([p.buffer(0) for p in parts])
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        area = sum(_area_km2(p) for p in polys)
        c = geom.centroid
        rows.append({
            "tract_code": a["cusec"],
            "municipality": a["nmun"],
            "code5": f"{a['cdis']}{a['csec']}",
            "lat": round(c.y, 6),
            "lon": round(c.x, 6),
            "area_km2": round(area, 5),
        })
    return pd.DataFrame(rows)


# ---- ADRH statistics ------------------------------------------------------------


def fetch_table(table_id: int, last_n: int = 3) -> list[dict]:
    data = _get_json(TEMPUS.format(table=table_id, n=last_n))
    if not isinstance(data, list):
        raise INEError(f"INE table {table_id} returned an unexpected payload: {str(data)[:200]}")
    return data


def parse_series(series: Iterable[dict], indicators: Iterable[str]) -> pd.DataFrame:
    """Long frame [municipality, code5, indicator, value, year] of section-level series.

    Keeps the latest non-empty year per series; suppressed values are dropped.
    Series names look like "Barcelona sección 01003. Población. Dato base. "
    (demographics) or "... sección 01003. Dato base. Renta neta media por hogar. "
    (income).
    """
    wanted = set(indicators)
    rows = []
    for s in series:
        m = _SERIES_RE.match(s.get("Nombre", ""))
        if not m:
            continue
        parts = [p.strip() for p in m.group("rest").split(".") if p.strip()]
        ind = next((p for p in parts if p in wanted), None)
        if ind is None:
            continue
        points = [p for p in s.get("Data", []) if p.get("Valor") is not None and not p.get("Secreto")]
        if not points:
            continue
        latest = max(points, key=lambda p: p["Anyo"])
        rows.append({"municipality": m.group("muni"), "code5": m.group("code"),
                     "indicator": ind, "value": float(latest["Valor"]), "year": int(latest["Anyo"])})
    return pd.DataFrame(rows, columns=["municipality", "code5", "indicator", "value", "year"])


def build_tract_frame(sections: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """Join polygons to statistics and derive the data/ine/<city>.csv schema."""
    wide = stats.pivot_table(index=["municipality", "code5"], columns="indicator",
                             values="value", aggfunc="first")
    years = stats.pivot_table(index=["municipality", "code5"], columns="indicator",
                              values="year", aggfunc="first")
    df = sections.merge(wide, left_on=["municipality", "code5"], right_index=True, how="left")
    df = df.merge(years.add_suffix("__year"), left_on=["municipality", "code5"],
                  right_index=True, how="left")

    out = pd.DataFrame({
        "tract_code": df["tract_code"],
        "municipality": df["municipality"],
        "lat": df["lat"],
        "lon": df["lon"],
        "area_km2": df["area_km2"],
        "population": df.get(POPULATION),
        "income_household": df.get(INCOME_HOUSEHOLD),
        "income_per_capita": df.get(INCOME_PERSON),
        "pct_foreign": 100.0 - df[PCT_SPANISH] if PCT_SPANISH in df else None,
        "population_year": df.get(f"{POPULATION}__year"),
        "income_year": df.get(f"{INCOME_HOUSEHOLD}__year"),
    })
    out["population_density"] = (out["population"] / out["area_km2"]).where(out["area_km2"] > 0)
    out = out.dropna(subset=["population"]).reset_index(drop=True)
    return out[["tract_code", "municipality", "lat", "lon", "area_km2", "population",
                "population_density", "income_household", "income_per_capita",
                "pct_foreign", "population_year", "income_year"]]
