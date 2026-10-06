# Data sources, licences and attribution

The **code** in this repository is MIT-licensed ([LICENSE](LICENSE)). The
**data** keeps the licence of its source, as listed below. If you reuse any
data file, keep the attribution shown here.

| Data | Where in the repo | Source | Licence | Required attribution |
|------|-------------------|--------|---------|----------------------|
| Points of interest (restaurants, shops, transit, hotels, offices, bars), aggregated per H3 hex | `data/sample_output/*.json` | [OpenStreetMap](https://www.openstreetmap.org) via the Overpass API | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) | "© OpenStreetMap contributors" |
| Census-tract population, net income, nationality share | `data/ine/*.csv`, and inside `data/sample_output/*.json` | [INE](https://www.ine.es), Atlas de Distribución de Renta de los Hogares (2023) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ([INE legal notice](https://www.ine.es/dyngs/AYU/index.htm?cid=125)) | "Elaboración propia con datos extraídos del sitio web del INE: www.ine.es" |
| Census-tract boundaries (used to compute centroids and areas; polygons not redistributed) | — | INE ADRH map service | CC BY 4.0 | as above |
| Hotel beds and overnight stays per municipality | `src/cities.py` | INE, Encuesta de Ocupación Hotelera (2024) | CC BY 4.0 | as above |
| City-median income (fallback only) | `src/cities.py` | INE ADRH (2022) | CC BY 4.0 | as above |
| Municipal population density (fallback only) | `src/cities.py` | INE Padrón (2024) / municipal area | CC BY 4.0 | as above |
| Crime per 1,000 residents | `src/cities.py` | Ministerio del Interior, *Balance de Criminalidad* (2024-Q4); Barcelona and Madrid open-data portals | Spanish public-sector information, free reuse with attribution (Ley 37/2007) | "Fuente: Ministerio del Interior; Ajuntament de Barcelona; Ayuntamiento de Madrid" |
| Neighbourhood rent benchmarks (€/sqm/month) | `data/rent/*.csv` | Figures cited from Cushman & Wakefield and CBRE Spain 2024 public retail reports, rounded and transcribed by the author | Facts cited with attribution; no report text, charts or logos are reproduced | "Rent benchmarks cited from Cushman & Wakefield and CBRE Spain 2024 public reports" |
| Map tiles (displayed in the app, not stored) | — | OpenStreetMap standard tiles (`tile.openstreetmap.org`), darkened client-side with a CSS filter | ODbL data; [OSMF Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/): attribution required, light use only, no bulk downloading | "© OpenStreetMap contributors" |
| Hexagonal grid | — | [Uber H3](https://h3geo.org) library | Apache 2.0 | — |

## The snapshot database (`data/sample_output/*.json`)

Each snapshot combines OpenStreetMap-derived counts with INE statistics, which
makes it a *Derivative Database* of OpenStreetMap. It is therefore made
available under the **Open Database License (ODbL) 1.0**, with the INE content
under CC BY 4.0 attribution. You may reuse it if you keep both attributions
and share any adapted database under the ODbL.

## Optional sources that are never published

These code paths exist so you can use data you are licensed to use
**privately**. Their output is never committed or deployed:

- **Google Places** (`scripts/pull_live_data.py --places`). Google Maps
  Platform terms forbid showing Places content on a non-Google map and limit
  caching. Output goes to `data/private/` (gitignored). CI rejects committed
  snapshots that contain Places data, and the app hides its map when one is
  loaded and shows Google attribution.
- **Licensed rent listings** (`scripts/import_rent_listings.py`). Import only
  data you have the right to use (a broker export, a purchased data feed, your
  own survey). This project contains no web scrapers: listing portals' terms
  forbid scraping, and Spanish law protects their databases (*sui generis*
  database right).

## Commercial use

The code is MIT, so you may use it commercially. Some data and services are
restricted, however. The OpenStreetMap tile servers are for light use only:
a high-traffic or commercial deployment must switch to a commercial or
self-hosted tile provider (one line in `src/viz/maps.py`). Re-check each
source's terms before any commercial use.
