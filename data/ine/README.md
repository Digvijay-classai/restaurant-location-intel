# INE census-tract demographics

`<city>.csv` holds one row per **sección censal** (census tract) inside the
city's bounding box, including neighbouring municipalities. Fetch or
refresh it from INE (free, no key):

```bash
python scripts/fetch_ine_tracts.py barcelona
python scripts/pull_live_data.py barcelona     # rebuild the snapshot with it
```

| Column | Source |
|--------|--------|
| `tract_code` | INE section code (`cusec`) |
| `municipality` | INE municipality name |
| `lat`, `lon` | Section polygon centroid (WGS84) |
| `area_km2` | Section polygon area |
| `population`, `population_year` | ADRH "Indicadores demográficos": Población (Padrón) |
| `population_density` | population / area_km2 |
| `income_household`, `income_per_capita`, `income_year` | ADRH "Indicadores de renta media": renta neta media por hogar / por persona |
| `pct_foreign` | 100 − ADRH "Porcentaje de población española" |

Sources:
- Section polygons: INE ADRH map service, `https://www.ine.es/servergis/rest/services/Hosted/Renta_media_por_hogar/FeatureServer/2`
- Statistics: INE Tempus API, `https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/<id>`. The per-province
  table ids are in `src/cities.py` (`ine_population_table`, `ine_income_table`); list all with
  `https://servicios.ine.es/wstempus/js/ES/TABLAS_OPERACION/353`.

Each value is the latest year INE publishes for that tract (currently
2023). INE suppresses a few small tracts' income for statistical secrecy;
those rows keep their population and the income is imputed at join time.

**Join to hexes:** every tract whose centroid lies within 1 km of the hex
centre contributes. That is the same catchment the revenue model uses:
density = residents in the disc / disc area, and income and foreign share
are population-weighted.

If the CSV is absent, demographics fall back to city medians in
`src/cities.py` (`demographics_source=city_median`), and the app withholds
verdicts.

Licence: census data © INE, reused under CC BY 4.0. Attribution: "Elaboración propia con datos extraídos del sitio web del INE: www.ine.es". See [DATA_LICENSES.md](../../DATA_LICENSES.md).
