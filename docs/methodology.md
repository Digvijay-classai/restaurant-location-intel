# Methodology

## The question

> "Where in this city should I open a restaurant?"

Operators usually answer this with broker introductions and footwork. That
is slow, hard to compare across cities, and anchors on the first few
neighbourhoods you look at. This tool gives a reproducible, sourced first
pass. Treat it as a shortlist to walk, not a lease decision.

## The approach in one picture

```
City boundary ──► H3 hex grid (res 8, ~0.74 km²)
                        │
                        ▼
                 ┌──────────────┐
   OSM POIs ───► │ restaurants  │
                 │ shops, offices, transit, hotels, bars…
   INE  ───────► │ income, population, foreign share (census tracts, 1 km disc)
   Crime ──────► │ official municipal rate × neighbourhood index (estimate)
   Rent CSV ───► │ €/sqm/month (author estimates or licensed listings)
                 └──────┬───────┘
                        ├──► 8 component scores ──► composite 0-100 (screen)
                        └──► unit economics ──► payback, downside/upside ──► RANK
```

Two views per hex, deliberately independent:

- The **composite** is a weighted sum of eight 0-1 components. It colours
  the map and breaks ties.
- The **unit economics** (revenue, costs, payback) are computed from demand
  inputs only. The composite is *not* an input to revenue. The **rank** is
  economics-first (see "Ranking").

## Eight component scores

| Component | What it measures | Signal |
|-----------|------------------|--------|
| Competition gap | `exp(-0.5 × same-cuisine restaurants over hex + 1-ring)` | OSM `cuisine=*` (exact tokens), optionally Google Places |
| Foot traffic | Daypart-blended pedestrian proxy, min-max within the city | Offices/shops/transit (lunch), bars/hotels/attractions (dinner) |
| Income match | Gaussian around the cuisine's ideal household income (σ = €10k) | INE Atlas de Renta |
| Tourism intensity | Hotels ×1.5 + attractions over hex + 1-ring, min-max within the city | OSM |
| Restaurant ecosystem | Bell curve peaking at ~14 restaurants (hex + neighbours) | OSM |
| Spend capacity | `0.6 × income_norm + 0.4 × everyday activity` (transit, offices, shops) | INE + OSM |
| Rent affordability | Logistic of estimated rent against the budget tier ceiling | Rent CSV + model |
| Safety | `exp(-crime / 120)` | Official municipal rate (Ministerio del Interior, 2025) × estimated neighbourhood index |

Plus a per-hex **confidence** in [0, 1]: 60% POI density (log scale,
saturating at 100 POIs) + 40% demographics (measured INE tracts = 1.0,
estimated = 0.5). The sidebar filters out low-confidence zones *before*
ranking.

### Edge-smoothing

A competitor 200 m away in the next hex competes for the same customer.
Competition, ecosystem, foot traffic and tourism are computed over the hex
plus its 6 neighbours (neighbours weighted 0.4-0.6). At the edge of the
study area, missing neighbours are imputed with the mean of the neighbours
present, so boundary hexes don't look artificially empty.

> Note: before v0.3 this smoothing silently never ran (an h3 v4 API change
> was swallowed by a bare `except`). Tests now cover it on real H3 cells.

### Daypart

Offices feed lunch; nightlife and hotels feed dinner. Each cuisine has a
lunch share (`src/cuisines.py`, e.g. burger 60%, Japanese 42%) that tilts
foot traffic and splits covers between lunch and dinner tickets.

### No constant offsets

City-level signals (hotel beds per 1,000) are identical for every hex in a
city. Adding them to per-hex scores only compresses the composite range
(v0.2 squeezed every city into ~47-80), so they are left out. Composites
compare zones *within* a city.

### Weights

Each cuisine has a weight profile (`src/scoring/weights.py`). The sidebar
lets you override every weight; weights are re-normalised to sum to 1.

## Unit economics

Per hex, per month, for a premises of `size_sqm` (default 150 sqm, 2.5
sqm/seat → 60 seats):

```
residents   = population density × 3.14 km² × 75% adults × 2.5% capture × 2.5 visits
visitors    = (hotels × 2,100 + attractions × 320) over hex + 1-ring × 1.2% capture
share       = 1 / (1 + 0.15 × same-cuisine competitors over hex + 1-ring)
demand      = (residents + visitors) × share
covers      = min(demand, seats × 2.2 turns × 26 days × 85%)
revenue     = covers × (lunch share × lunch ticket + dinner share × dinner ticket)

costs       = rent (€/sqm × size) + core team €5,550 + €3.40 labour per cover
              + fixed OpEx €12/sqm + food 30% of revenue
contribution = revenue − costs          (before tax and debt service)
break-even  = fixed costs / (ticket × 70% − €3.40)
capex       = size × (€1,067/sqm + €8/sqm per €1 of rent/sqm)
payback     = capex / contribution      (shown only if contribution > €2,000 and ≤ 120 months)
```

Labour lands at roughly 28-36% of revenue at healthy volumes, in line with
Hostelería de España 2024. Every direct competitor nearby takes a slice of
demand, so more competition never raises revenue.

**Sensitivity.** Each zone also gets a downside case (rent +20%, ticket
−10%, demand −30%) and an upside case (rent −20%, ticket +10%, demand
+30%). The brief reports both. A zone that only works in the base case
should be negotiated hard or skipped.

## Ranking

One `rank` column drives the map pins, the Rankings table and the
Shortlist:

1. **Viable:** feasible (covers > break-even), in a named neighbourhood,
   payback within 10 years. Sorted by payback.
2. **Feasible, slow payback:** sorted by contribution.
3. **Below break-even:** sorted by composite.
4. **Outskirts** (outside the named neighbourhood set): sorted by composite.

## Verdicts and data provenance

Every snapshot records where its inputs came from (`meta.sources`) and
when (`meta.vintages`). The app shows this first, above everything else.

| Data state | What the app does |
|---|---|
| Synthetic POIs/demographics | Amber SYNTHETIC banner; numbers shown; **no verdicts** |
| Live OSM POIs, city-median demographics | Blue banner; numbers shown; **no verdicts** |
| Live OSM POIs + INE tract demographics | Green banner; verdicts in briefs |

Without tract demographics every hex shares the same income and
population density, so resident demand is a city average. That is good
enough to compare competition, footfall and rent, but not to say "sign
here".

**Demographics join.** `scripts/fetch_ine_tracts.py` downloads every
census tract in the city's bounding box from INE: polygons, population,
net income and foreign share (latest year, currently 2023). Each hex
aggregates the tracts whose centroid lies within 1 km of its centre, the
same disc the revenue model uses. Density is residents in the disc divided
by the disc area; income and foreign share are population-weighted.

**Known calibration gap.** Demand shrinks only with same-cuisine
competitors. In dense cores, 2.5% of the adults within 1 km often exceeds
a 60-seat room's capacity, so many zones are capacity-capped and the
ranking leans on rent. A backtest against real openings and closures, or
an all-restaurant saturation term, is needed before relying on absolute
paybacks.

## Data sources

| Source | Data | Access | Cost |
|--------|------|--------|------|
| OpenStreetMap via Overpass | Restaurants, shops, transit, hotels, offices, bars | Open, no key | Free |
| INE Atlas de Renta de los Hogares | Household income per census tract | Open CSV (`data/ine/`) | Free |
| Ministerio del Interior, Balance de Criminalidad Q4 2025 | Municipal crime count (rate = count / INE population) | Static, 2025 | Free |
| Google Places API (optional) | Competitor counts (refresh only) | API key | Free tier |
| Author estimates (calibrated to Cushman & Wakefield / CBRE Spain 2024 ranges) | Rent per neighbourhood | `data/rent/` | — |
| Uber H3 | Hexagonal spatial indexing | Library | Free |

## Limitations

- **Foot traffic is proxied** from static POIs, not measured counts.
- **Rent is a seeded neighbourhood figure blended with a model.** It misses
  micro-location effects (corner premium, metro exits).
- **Demographics are census-tract level**, aggregated over a 1 km disc,
  and only when `data/ine/<city>.csv` exists; otherwise they are city
  medians.
- **Neighbourhoods are circles around centroids**, so ~20-30% of hexes fall
  into "Outskirts".
- **Licence/BIC flags are district-level.** Verify the sub-barrio (BCN Pla
  Especial d'Usos, MAD BIC perimeters) before signing.
- **Catchments overlap.** Neighbouring hexes share most residents; compare
  zones one at a time, don't sum them.
- **The model is not backtested** against real openings and closures yet
  (see TODOS.md).
- **Standalone dine-in only:** not ghost kitchens, food courts or
  delivery-only concepts.
