# Commercial rent per neighbourhood

The CSVs here follow the schema:

```csv
neighbourhood,eur_per_sqm_month,n_listings,source
Eixample,78.00,91,seeded_cw_cbre_2024
Gracia,46.00,31,seeded_cw_cbre_2024
...
```

Neighbourhood names are matched case- and accent-insensitively, ignoring
hyphens (`Sarria-Sant Gervasi` = `sarria sant gervasi`). The `source` column
is shown in the app's provenance bar.

## Shipped values

The three files (`barcelona.csv`, `madrid.csv`, `valladolid.csv`) are
**seeded**: each neighbourhood figure is cited from Cushman & Wakefield and
CBRE Spain 2024 public retail reports, then rounded and transcribed by the
author. `n_listings` is the weight given to that figure in the blend; it is
not a count of real listings.

The pipeline blends each value with a modelled proxy using Bayesian
shrinkage (prior strength `k=15`). Neighbourhoods with a small weight lean
on the model; those with a large weight lean on the figure.

## Importing real listings you are licensed to use

```bash
python scripts/import_rent_listings.py barcelona my_listings.csv --source broker_export_2026-10
```

The listings CSV needs `monthly_rent_eur`, `size_sqm`, and either
`neighbourhood` or `lat` + `lon`. Listings outside 20-2,000 sqm are
ignored; a neighbourhood needs at least 3 listings. Use broker exports,
purchased data feeds (e.g. Idealista Data, Habitaclia), or your own survey.
Do not scrape listing portals: their terms forbid it, and Spanish law
protects their databases.

Licence: see [DATA_LICENSES.md](../../DATA_LICENSES.md).
