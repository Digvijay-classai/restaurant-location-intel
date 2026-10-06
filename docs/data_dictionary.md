# Data dictionary

Columns in the DataFrame returned by `run_pipeline` / `run_pipeline_with_meta`.

## Snapshot meta (`run_pipeline_with_meta(...).meta`)

| Key | Values |
|-----|--------|
| `sources.pois` | `synthetic` · `osm_overpass` |
| `sources.demographics` | `synthetic` · `ine_csv` · `city_median` · `mixed` |
| `sources.competitors` | `synthetic` · `osm` · `google_places` |
| `sources.boundary` | `geojson` · `bbox` |
| `vintages.*` | Human-readable vintage per source |
| `rent` | Rent CSV `source` column: `seeded_cw_cbre_2024`, the `--source` label of an import, or `none` |
| `generated_with`, `generated_at` | Producer and UTC timestamp (none for deterministic synthetic) |

## Identifiers

| Column | Type | Description |
|--------|------|-------------|
| `h3_id` | str | Uber H3 cell id at resolution 8 |
| `center_lat`, `center_lon` | float | Cell centre (WGS84) |
| `neighbourhood` | str | Nearest named neighbourhood, or `Outskirts` |

## POI counts (per hex)

| Column | Source | Notes |
|--------|--------|-------|
| `restaurant` | OSM `amenity=restaurant` (or Google Places when `competitor_source=google_places`) | Total restaurants |
| `shop` | OSM `shop=*` | |
| `transit` | OSM `public_transport=station` | Metro / rail stations |
| `bus_stop` | OSM `highway=bus_stop` | Weighted 0.4 in foot traffic |
| `tourism` | OSM `tourism=attraction\|museum\|gallery\|viewpoint\|artwork` | |
| `hotel` | OSM `tourism=hotel\|hostel\|guest_house` | |
| `office` | OSM `office=*` | Daytime demand |
| `nightlife` | OSM `amenity=bar\|pub\|nightclub` | Night-time demand |
| `cuisine_counts` | OSM `cuisine=*` | Dict cuisine → count (exact tokens; a "pizza;burger" place counts for both) |
| `same_cuisine` | derived | Selected cuisine's count in this hex |
| `same_cuisine_ring` | derived | Same-cuisine over hex + 1-ring (neighbours ×0.5) |
| `competitor_source` | derived | `osm`, `google_places` or `synthetic` |

## Demographics (per hex, nearest-tract join)

| Column | Notes |
|--------|-------|
| `income_household` | EUR / household / year |
| `income_per_capita` | EUR / capita / year |
| `pct_foreign` | % foreign-born |
| `population_density` | people / km² |
| `demographics_source` | `ine_csv`, `city_median`, `synthetic` or `imputed` (NaN filled from the frame median) |

## Location context

| Column | Notes |
|--------|-------|
| `crime_per_1000` | Neighbourhood rate, else city rate |
| `listing_rent`, `listing_n` | Rent CSV value and listing count for the neighbourhood |
| `rent_source` | `listings+model` or `model` |
| `est_rent_eur_sqm` | Blended rent, EUR / sqm / month, clipped to [10, 220] |

## Scores

| Column | Range | Description |
|--------|-------|-------------|
| `competition_gap` … `safety` | [0, 1] | The 8 components (see methodology) |
| `confidence` | [0, 1] | Data density + measured demographics |
| `composite` | 0-100 | Weighted sum of the 8 components |

## Unit economics (per month unless noted)

| Column | Description |
|--------|-------------|
| `size_sqm`, `seats` | Premises size and seats (2.5 sqm/seat) |
| `competition_share` | Share of demand kept after nearby same-cuisine competitors |
| `capacity_capped` | Demand exceeded seat capacity |
| `projected_covers_per_month`, `lunch_covers_per_month`, `dinner_covers_per_month` | Covers |
| `blended_ticket_eur` | Average ticket per cover |
| `monthly_revenue_eur` | Revenue |
| `monthly_rent_eur`, `monthly_labour_eur`, `monthly_food_eur`, `monthly_other_eur` | Cost lines |
| `monthly_contribution_eur` | Revenue minus all costs above (before tax and debt) |
| `breakeven_covers_per_month` | Covers needed to cover fixed costs |
| `concept_feasible` | Projected covers > break-even covers |
| `capex_eur` | Fit-out + licensing (one-off) |
| `payback_months` | capex / contribution; `inf` if contribution ≤ €2,000 or payback > 120 months |
| `contribution_low_eur`, `payback_low_months` | Downside case (rent +20%, ticket −10%, demand −30%) |
| `contribution_high_eur`, `payback_high_months` | Upside case |
| `risk_flags` | List of strings (licence/BIC, saturation, crime, prime rent, below break-even, capacity, low confidence) |

## Ranking

| Column | Description |
|--------|-------------|
| `rank_tier` | 0 viable · 1 feasible, slow payback · 2 below break-even · 3 Outskirts |
| `rank` | 1 = best; shared by map pins, Rankings table and Shortlist |
