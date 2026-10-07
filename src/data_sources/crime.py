"""Crime / safety index per municipality and neighbourhood.

Spain's Ministerio del Interior publishes `Balance de Criminalidad`
quarterly (`infracciones penales convencionales / 1,000 habitantes`,
registered residents). Barcelona and Madrid additionally publish
district-level incident counts via their open-data portals; Valladolid
Policia Municipal publishes zone-level figures as PDF reports.

Note on measurement: dividing crimes by *registered residents* inflates
tourist-city rates (daily population is 2-4x resident count in
Ciutat Vella, Centro Madrid, etc.). We embrace that — an operator cares
about absolute incident risk per block, not per-capita-normalised-only.

Safety score: `safety = exp(-crime / 120)`.
0 crime -> 1.0, 60 -> 0.61, 120 -> 0.37, 240 -> 0.14.

Municipal rate (official): Ministerio del Interior, Balance de
Criminalidad Q4 2025, "Criminalidad convencional" Jan-Dec 2025, divided by
INE ADRH 2023 municipal population. Neighbourhood variation is an AUTHOR
ESTIMATE (relative index in `src/cities.py`), because the Ministry publishes
municipal totals only.
Sources:
- https://estadisticasdecriminalidad.ses.mir.es
- https://opendata-ajuntament.barcelona.cat (incidents por districte)
- https://datos.madrid.es (seguridad y emergencias)
- Policia Municipal Valladolid memoria anual
"""
from __future__ import annotations

from ..cities import CITIES, CRIME_VINTAGE  # noqa: F401  (re-exported)

DEFAULT_CRIME_PER_1000 = 55.0


def city_crime_rate(city: str) -> float:
    c = CITIES.get(city.lower())
    return c.crime_per_1000 if c else DEFAULT_CRIME_PER_1000


def neighbourhood_crime_rate(city: str, neighbourhood: str) -> float:
    """Official municipal rate x the neighbourhood's estimated relative index.

    Neighbourhoods without an index (and "Outskirts") get the municipal rate.
    """
    c = CITIES.get(city.lower())
    if c is None:
        return DEFAULT_CRIME_PER_1000
    return c.crime_per_1000 * c.hood_crime_index.get(neighbourhood, 1.0)
