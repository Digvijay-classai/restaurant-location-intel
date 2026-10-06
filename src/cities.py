"""Single registry of everything the pipeline knows about a city.

Adding a city means adding one `City` entry below plus (optionally) data
files under `data/` — see CONTRIBUTING.md. Every other module reads from
here instead of keeping its own per-city dict.

Data vintages are recorded next to the values so the UI can show them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CRIME_VINTAGE = "2024-Q4 (Ministerio del Interior, rolling 12-month)"
TOURISM_VINTAGE = "2024 average (INE Encuesta de Ocupacion Hotelera)"
INCOME_VINTAGE = "2022 (INE Atlas de Distribucion de Renta de los Hogares)"
DENSITY_VINTAGE = "2024 municipal average (INE Padron / municipal area)"


@dataclass(frozen=True)
class City:
    key: str
    name: str
    center: tuple[float, float]          # (lat, lon)
    radius_deg: float                    # bbox half-size when no GeoJSON boundary exists
    # (name, lat, lon, radius_km): nearest-centroid neighbourhood lookup.
    hoods: tuple[tuple[str, float, float, float], ...]
    crime_per_1000: float                # municipality rate
    hood_crime_per_1000: dict[str, float]
    hotel_beds_per_1000: float
    overnight_stays_per_capita: float
    income_household: float              # city median, EUR / household / year
    income_per_capita: float
    pct_foreign: float
    # Municipal residents per km2 (INE Padron 2024 / municipal area, approx.).
    # Only used when no tract CSV exists. Understates dense urban cores in
    # municipalities with large non-urban land (Madrid's El Pardo, Valladolid).
    population_density: float
    # INE Tempus table ids for the province's ADRH section-level tables
    # ("Indicadores demograficos", "Indicadores de renta media y mediana"),
    # used by scripts/fetch_ine_tracts.py. Find them via
    # https://servicios.ine.es/wstempus/js/ES/TABLAS_OPERACION/353
    ine_population_table: int | None = None
    ine_income_table: int | None = None
    # Neighbourhoods whose district overlaps a licensing moratorium or
    # heritage (BIC) perimeter. The real polygons are smaller than the
    # district, so the flag copy says "verify sub-barrio".
    licence_restricted: frozenset[str] = field(default_factory=frozenset)
    # Synthetic demo generator calibration (scripts/build_demo_data.py).
    synthetic_radius_deg: float = 0.040
    synthetic_income_sd: float = 10_000.0
    synthetic_cuisine_share: dict[str, float] = field(default_factory=dict)


CITIES: dict[str, City] = {
    "barcelona": City(
        key="barcelona",
        name="Barcelona",
        center=(41.3874, 2.1686),
        radius_deg=0.055,
        hoods=(
            ("Ciutat Vella",        41.3806, 2.1770, 1.4),
            ("Eixample",            41.3900, 2.1620, 2.0),
            ("Sants-Montjuic",      41.3680, 2.1360, 2.4),
            ("Les Corts",           41.3870, 2.1300, 1.6),
            ("Sarria-Sant Gervasi", 41.4020, 2.1340, 2.6),
            ("Gracia",              41.4030, 2.1570, 1.5),
            ("Horta-Guinardo",      41.4190, 2.1680, 2.4),
            ("Nou Barris",          41.4420, 2.1770, 2.2),
            ("Sant Andreu",         41.4350, 2.1890, 2.0),
            ("Sant Marti",          41.4100, 2.2010, 2.6),
            # Adjacent municipalities within the bbox:
            ("L'Hospitalet",        41.3600, 2.1030, 2.5),
            ("Badalona",            41.4500, 2.2470, 2.8),
            ("Santa Coloma",        41.4530, 2.2110, 1.6),
            ("Esplugues",           41.3760, 2.0870, 1.6),
        ),
        crime_per_1000=73.4,
        hood_crime_per_1000={
            # Ciutat Vella tourist-theft inflator (daily pop. ~3x resident).
            "Ciutat Vella": 238.0, "Eixample": 87.0, "Sants-Montjuic": 62.0,
            "Les Corts": 41.0, "Sarria-Sant Gervasi": 36.0, "Gracia": 58.0,
            "Horta-Guinardo": 44.0, "Nou Barris": 56.0, "Sant Andreu": 47.0,
            "Sant Marti": 61.0,
        },
        hotel_beds_per_1000=48.0,
        overnight_stays_per_capita=11.5,
        income_household=36_500, income_per_capita=15_200, pct_foreign=23.0,
        population_density=16_800,
        ine_population_table=30904, ine_income_table=30896,
        # BCN Pla Especial d'Usos: Ciutat Vella, Eixample sub-zones, Vila de Gracia.
        licence_restricted=frozenset({"Ciutat Vella", "Eixample", "Gracia"}),
        synthetic_income_sd=11_000,
        synthetic_cuisine_share={
            "italian": 0.26, "japanese": 0.14, "mediterranean": 0.20,
            "chinese": 0.09, "mexican": 0.08, "indian": 0.07,
            "burger": 0.11, "thai": 0.05,
        },
    ),
    "madrid": City(
        key="madrid",
        name="Madrid",
        center=(40.4168, -3.7038),
        radius_deg=0.090,
        hoods=(
            ("Centro",              40.4150, -3.7036, 1.2),
            ("Arganzuela",          40.3980, -3.6960, 1.8),
            ("Retiro",              40.4100, -3.6760, 1.5),
            ("Salamanca",           40.4290, -3.6770, 1.6),
            ("Chamartin",           40.4560, -3.6770, 1.8),
            ("Tetuan",              40.4600, -3.6990, 1.6),
            ("Chamberi",            40.4360, -3.6980, 1.3),
            ("Fuencarral-El Pardo", 40.4850, -3.7080, 3.5),
            ("Moncloa-Aravaca",     40.4440, -3.7290, 2.5),
            ("Latina",              40.4000, -3.7400, 2.2),
            ("Carabanchel",         40.3830, -3.7340, 2.2),
            ("Usera",               40.3810, -3.7120, 1.6),
            ("Puente de Vallecas",  40.3870, -3.6670, 2.0),
            ("Moratalaz",           40.4080, -3.6460, 1.6),
            ("Ciudad Lineal",       40.4420, -3.6540, 2.0),
            ("Hortaleza",           40.4720, -3.6400, 2.5),
            ("Villaverde",          40.3500, -3.7100, 2.4),
            ("Villa de Vallecas",   40.3800, -3.6160, 2.5),
            ("Vicalvaro",           40.4040, -3.6080, 2.4),
            ("San Blas-Canillejas", 40.4310, -3.6160, 2.4),
            ("Barajas",             40.4760, -3.5840, 2.4),
        ),
        crime_per_1000=61.2,
        hood_crime_per_1000={
            "Centro": 196.0, "Arganzuela": 62.0, "Retiro": 47.0,
            "Salamanca": 68.0, "Chamartin": 43.0, "Tetuan": 69.0,
            "Chamberi": 54.0, "Fuencarral-El Pardo": 36.0,
            "Moncloa-Aravaca": 46.0, "Latina": 57.0, "Carabanchel": 64.0,
            "Usera": 71.0, "Puente de Vallecas": 76.0, "Moratalaz": 40.0,
            "Ciudad Lineal": 52.0, "Hortaleza": 38.0, "Villaverde": 73.0,
            "Villa de Vallecas": 48.0, "Vicalvaro": 44.0,
            "San Blas-Canillejas": 53.0, "Barajas": 39.0,
        },
        hotel_beds_per_1000=32.0,
        overnight_stays_per_capita=7.1,
        income_household=38_200, income_per_capita=16_400, pct_foreign=19.0,
        population_density=5_700,
        ine_population_table=31105, ine_income_table=31097,
        # MAD BIC perimeter (Sol/Lavapies/Austrias in Centro) and Barrio
        # Salamanca conservation area.
        licence_restricted=frozenset({"Centro", "Salamanca"}),
        synthetic_radius_deg=0.065,
        synthetic_income_sd=13_500,
        synthetic_cuisine_share={
            "italian": 0.25, "japanese": 0.12, "mediterranean": 0.22,
            "chinese": 0.10, "mexican": 0.09, "indian": 0.07,
            "burger": 0.11, "thai": 0.04,
        },
    ),
    "valladolid": City(
        key="valladolid",
        name="Valladolid",
        center=(41.6523, -4.7245),
        radius_deg=0.045,
        hoods=(
            ("Centro",                41.6523, -4.7245, 0.9),
            ("San Pablo",             41.6600, -4.7140, 0.7),
            ("Delicias",              41.6350, -4.7310, 1.2),
            ("La Rondilla",           41.6630, -4.7220, 1.0),
            ("Huerta del Rey",        41.6530, -4.7490, 1.2),
            ("Parquesol",             41.6460, -4.7620, 1.4),
            ("Pajarillos",            41.6560, -4.6970, 1.4),
            ("La Victoria",           41.6710, -4.7340, 1.0),
            ("Barrio Espana",         41.6700, -4.7420, 0.9),
            ("Belen",                 41.6440, -4.7020, 1.0),
            ("Las Flores",            41.6260, -4.7360, 1.1),
            ("Hospital",              41.6490, -4.7130, 0.8),
            ("San Isidro",            41.6210, -4.7250, 1.0),
            ("Pajarillos-Industrial", 41.6160, -4.6980, 1.3),
            ("Villa del Prado",       41.6400, -4.7700, 1.2),
            ("Covaresa",              41.6250, -4.7620, 1.3),
            ("Zona Universidad",      41.6650, -4.7050, 1.0),
            ("Pilarica",              41.6450, -4.6890, 1.0),
        ),
        crime_per_1000=42.1,
        hood_crime_per_1000={
            "Centro": 62.0, "San Pablo": 48.0, "Delicias": 44.0,
            "La Rondilla": 41.0, "Huerta del Rey": 35.0, "Parquesol": 29.0,
            "Pajarillos": 54.0, "La Victoria": 33.0, "Barrio Espana": 46.0,
            "Belen": 36.0, "Las Flores": 38.0, "Hospital": 42.0,
            "San Isidro": 40.0, "Pajarillos-Industrial": 51.0,
            "Villa del Prado": 31.0, "Covaresa": 28.0,
            "Zona Universidad": 37.0, "Pilarica": 43.0,
        },
        hotel_beds_per_1000=11.5,
        overnight_stays_per_capita=2.4,
        income_household=33_800, income_per_capita=14_100, pct_foreign=10.5,
        population_density=1_500,
        ine_population_table=31267, ine_income_table=31259,
        licence_restricted=frozenset(),
        synthetic_income_sd=7_500,
        synthetic_cuisine_share={
            "italian": 0.30, "japanese": 0.06, "mediterranean": 0.28,
            "chinese": 0.08, "mexican": 0.08, "indian": 0.04,
            "burger": 0.14, "thai": 0.02,
        },
    ),
}

CITY_KEYS: list[str] = sorted(CITIES)


def get_city(city: str) -> City:
    """Return the registry entry, or raise with the fix spelled out."""
    key = city.strip().lower()
    if key not in CITIES:
        raise ValueError(
            f"Unknown city {city!r}. Known cities: {', '.join(CITY_KEYS)}. "
            "To add one, add a City entry in src/cities.py (see CONTRIBUTING.md)."
        )
    return CITIES[key]
