# TODOS

Deferred work from the /autoplan review of 2026-10-06 (commit 77f5b47). Goal: real operator tool.
Effort is shown as human team → Claude Code.

## P1: needed before an operator should trust a ranking

### Backtest the score against real openings and closures
- **What:** check whether high-ranked zones actually had better restaurant survival.
- **Why:** the weights are hand-tuned. Nothing shows that the ranking predicts success.
- **Context:** candidate sources are the Barcelona Cens d'activitats and the Madrid Censo de locales, both with open/close dates, plus OSM history. Start with Barcelona, which has the best open data.
- **Effort:** L → M
- **Depends on:** the scoring and economics fixes in this review.

### Calibrate demand saturation
- **What:** add competition from all restaurants nearby, not only same-cuisine ones, and tune the 2.5% capture rate. Fit both against the backtest.
- **Why:** with real INE densities, demand hits a 60-seat room's capacity in up to 80% of "viable" zones in dense Barcelona and Madrid. The ranking then leans on rent, and ~11-month paybacks are optimistic.
- **Effort:** M → S, after the backtest.

## P2

### Licensing and zoning polygons
- **What:** replace the district-level `LICENCE_RESTRICTED` set with the real polygons: the Barcelona Pla Especial d'Usos sub-zones and the Madrid BIC (protected-heritage) perimeters, keyed by city.
- **Why:** this is the one differentiator incumbent tools lack, and today's flag is district-wide.
- **Effort:** M → S, mostly data acquisition.

### Listing-level input
- **What:** take 3–10 candidate premises (address or listing reference, sqm, rent) and output a side-by-side memo with sensitivities.
- **Why:** operators choose among listings, not hexes.
- **Context:** this is User Challenge UC1 from the review. Do it only if the user accepts it. Keep scoring callable on any (lat, lon) point so this stays cheap.
- **Effort:** L → M

### License real rent data
- **What:** buy or partner for listing-level rent data (Idealista Data, Habitaclia, a broker) and load it with `scripts/import_rent_listings.py`.
- **Why:** the seeded neighbourhood figures miss micro-location premiums. The importer already exists; only the data is missing.
- **Effort:** S (decision) plus cost.

## P3

### More cities and a scheduled refresh
- **What:** a city registry makes adding a city a single entry. Add a quarterly refresh job that writes LIVE snapshots.
- **Effort:** M → S

### Design system
- **What:** run /design-consultation to replace the ad-hoc palette.
- **Effort:** S

### Full Spanish (es-ES) UI
- **What:** Spanish copy throughout. Number and € formatting already ship in the main plan.
- **Effort:** S
