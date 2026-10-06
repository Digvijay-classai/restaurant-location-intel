"""Tests for OSM parsing, cuisine matching, neighbourhoods, rent listings and Places."""
from __future__ import annotations

import pytest

from src.cities import get_city
from src.cuisines import matches, osm_cuisine_tokens
from src.data_sources import google_places, neighborhoods, overture_maps, rent_listings
from src.geo.boundaries import load_city_boundary



# ---- cuisine matching (regression: substring matches) -------------------------

def test_cuisine_tokens_split_on_semicolon():
    assert osm_cuisine_tokens("Pizza; Italian") == {"pizza", "italian"}
    assert osm_cuisine_tokens(None) == set()


@pytest.mark.parametrize("cuisine,tag,expected", [
    ("burger", "latin_american", False),   # was True via substring "american"
    ("burger", "american", True),
    ("italian", "pizza;burger", True),
    ("burger", "pizza;burger", True),
    ("thai", "thai_fusion", False),
    ("mexican", "tex-mex", True),
])
def test_cuisine_exact_match(cuisine, tag, expected):
    assert matches(cuisine, tag) is expected


# ---- Overpass parsing ---------------------------------------------------------

def test_query_includes_ways_and_relations():
    q = overture_maps._build_query((41.3, 2.1, 41.4, 2.2))
    assert "nwr[\"amenity\"=\"restaurant\"]" in q
    assert "out tags center" in q


def test_parse_elements_handles_nodes_and_way_centres():
    els = [
        {"type": "node", "lat": 41.39, "lon": 2.17, "tags": {"amenity": "restaurant", "cuisine": "italian"}},
        {"type": "way", "center": {"lat": 41.391, "lon": 2.171}, "tags": {"shop": "bakery"}},
        {"type": "way", "tags": {"shop": "bakery"}},  # no centre -> skipped
        {"type": "node", "lat": 41.39, "lon": 2.17, "tags": {"amenity": "bench"}},  # unclassified
    ]
    pois = overture_maps.parse_elements(els)
    assert [p.category for p in pois] == ["restaurant", "shop"]


def test_pois_to_hex_counts_counts_cuisines():
    els = [
        {"type": "node", "lat": 41.39, "lon": 2.17, "tags": {"amenity": "restaurant", "cuisine": "pizza;burger"}},
        {"type": "node", "lat": 41.39, "lon": 2.17, "tags": {"amenity": "restaurant", "cuisine": "latin_american"}},
    ]
    counts = overture_maps.pois_to_hex_counts(overture_maps.parse_elements(els))
    (bucket,) = counts.values()
    assert bucket["restaurant"] == 2
    assert bucket["cuisine_counts"]["italian"] == 1
    assert bucket["cuisine_counts"]["burger"] == 1


def test_fetch_pois_recovers_from_corrupt_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(overture_maps, "CACHE_DIR", tmp_path)
    (tmp_path / "osm_testcity.json").write_text("{not json")
    monkeypatch.setattr(overture_maps, "_download", lambda q: {"elements": [
        {"type": "node", "lat": 41.39, "lon": 2.17, "tags": {"office": "company"}}]})
    pois = overture_maps.fetch_pois("testcity", load_city_boundary("barcelona"))
    assert [p.category for p in pois] == ["office"]


def test_download_error_mentions_mirror(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(overture_maps.requests, "post", boom)
    monkeypatch.setattr(overture_maps.time, "sleep", lambda s: None)
    with pytest.raises(overture_maps.OverpassError, match="OVERPASS_URL"):
        overture_maps._download("q", attempts=2)


# ---- neighbourhoods / cities -----------------------------------------------------

def test_neighbourhood_lookup():
    assert neighborhoods.neighbourhood_for("barcelona", 41.3806, 2.1770) == "Ciutat Vella"
    assert neighborhoods.neighbourhood_for("madrid", 40.4150, -3.7036) == "Centro"
    assert neighborhoods.neighbourhood_for("madrid", 41.0, -3.0) == neighborhoods.OUTSKIRTS
    assert neighborhoods.neighbourhood_for("atlantis", 0, 0) == neighborhoods.OUTSKIRTS


def test_unknown_city_error_says_how_to_fix():
    with pytest.raises(ValueError, match="src/cities.py"):
        get_city("sevilla")


# ---- rent listings --------------------------------------------------------------

def test_normalise_name_joins_slug_and_display_names():
    n = rent_listings.normalise_name
    assert n("Sarria-Sant Gervasi") == n("Sarria Sant Gervasi") == n("sarria-sant-gervasi")
    assert n("Sarrià-Sant Gervasi") == "sarria sant gervasi"
    assert n("L'Hospitalet") == "l hospitalet"


def test_read_listings_csv_by_name_and_coordinates(tmp_path):
    f = tmp_path / "listings.csv"
    f.write_text(
        "Neighbourhood,monthly_rent_eur,size_sqm,lat,lon\n"
        "sarria-sant-gervasi,4500,90,,\n"          # name, accent/hyphen-insensitive
        ",3000,100,41.3806,2.1770\n"                # coordinates -> Ciutat Vella
        "Atlantis,1000,50,,\n"                      # unknown name -> skipped
        ",2000,80,41.0,1.0\n"                       # outside neighbourhoods -> skipped
        "Gracia,abc,80,,\n",                        # bad number -> skipped
        encoding="utf-8",
    )
    listings, warnings = rent_listings.read_listings_csv(f, "barcelona")
    assert [(x.neighbourhood, x.price_eur_month) for x in listings] == [
        ("Sarria-Sant Gervasi", 4500.0), ("Ciutat Vella", 3000.0)]
    assert len(warnings) == 3


def test_read_listings_csv_rejects_missing_columns(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("price,sqm\n1,2\n", encoding="utf-8")
    with pytest.raises(rent_listings.ListingsError, match="monthly_rent_eur"):
        rent_listings.read_listings_csv(f, "barcelona")


def test_aggregate_counts_after_size_filter():
    L = rent_listings.RentListing
    listings = [L("A", 3000, 100), L("A", 4000, 100), L("A", 5000, 100),
                L("A", 100, 5),        # too small: dropped from median AND count
                L("B", 3000, 100)]     # < 3 listings: omitted
    assert rent_listings.aggregate_by_neighbourhood(listings) == {"A": (40.0, 3)}


def test_import_script_round_trip(tmp_path, monkeypatch):
    from scripts import import_rent_listings
    monkeypatch.setattr(rent_listings, "OUT_DIR", tmp_path / "rent")
    f = tmp_path / "listings.csv"
    f.write_text("neighbourhood,monthly_rent_eur,size_sqm\n" + "Gracia,6000,100\n" * 3, encoding="utf-8")
    assert import_rent_listings.main(["barcelona", str(f), "--source", "broker_2026"]) == 0
    assert rent_listings.load_city_csv_full("barcelona") == {"gracia": (60.0, 3)}
    assert rent_listings.rent_source("barcelona") == "broker_2026"


def test_shipped_rent_csvs_are_labelled_seeded():
    for city in ("barcelona", "madrid", "valladolid"):
        assert rent_listings.rent_source(city) == "seeded_cw_cbre_2024"


# ---- Google Places -----------------------------------------------------------

class _Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload or {}, ""

    def json(self):
        return self._payload


def test_places_counts_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(google_places, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(google_places, "DB_PATH", tmp_path / "p.sqlite")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test")
    calls = []

    def post(url, json, headers, timeout):
        calls.append(json["includedTypes"])
        return _Resp(200, {"places": [{"id": "1"}, {"id": "2"}]})
    monkeypatch.setattr(google_places.requests, "post", post)
    assert google_places.count_restaurants(41.39, 2.17, "h1", "italian") == 2
    assert google_places.count_restaurants(41.39, 2.17, "h1", "italian") == 2  # cached
    assert calls == [["italian_restaurant"]]


def test_places_bad_key_message(tmp_path, monkeypatch):
    monkeypatch.setattr(google_places, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(google_places, "DB_PATH", tmp_path / "p.sqlite")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "bad")
    monkeypatch.setattr(google_places.requests, "post", lambda *a, **k: _Resp(403))
    with pytest.raises(google_places.PlacesError, match="Places API"):
        google_places.count_restaurants(41.39, 2.17, "h2", "thai")


def test_places_missing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(google_places, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(google_places, "DB_PATH", tmp_path / "p.sqlite")
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    with pytest.raises(google_places.PlacesError, match="GOOGLE_PLACES_API_KEY"):
        google_places.count_restaurants(41.39, 2.17, "h3", None)
