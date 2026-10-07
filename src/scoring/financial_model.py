"""Per-zone unit economics for a casual-dining restaurant in Spain.

Calibrated against the public 2024 reports a Spanish F&B operator would
quote:

- Hosteleria de Espana 2024 (personnel costs)
- KPMG Restaurant Spain 2024
- Cushman & Wakefield / CBRE Spain high-street benchmarks 2024

Demand model (per month):

    residents  = pop_density x 3.14 km2 x 75% adults x 2.5% capture x 2.5 visits
    visitors   = (hotels x 2,100 + tourist POIs x 320) over hex + 1-ring x 1.2% capture
    demand     = (residents + visitors) x competition_share
    covers     = min(demand, seat capacity)

`competition_share = 1 / (1 + 0.15 x same-cuisine competitors over hex +
1-ring)`: each direct competitor nearby takes a slice of the same
customers. The composite score is NOT an input here — economics and the
composite are independent views, and the ranking uses economics.

Costs: rent (EUR/sqm x size), a fixed core team, labour that scales per
cover, fixed OpEx, food COGS. Capex scales with size and rent level.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..cities import CITIES
from ..cuisines import day_share, tickets
from ..formatting import NO_PAYBACK, eur, eur_k, months, num, pct
from ..data_sources.neighborhoods import OUTSKIRTS
from .engine import ring_sum
from .weights import BUDGET_MAX_RENT

# --------- Operator-defined constants ----------------------------------------
REFERENCE_SIZE_SQM = 150.0
MIN_SIZE_SQM, MAX_SIZE_SQM = 60.0, 400.0
SQM_PER_SEAT = 2.5                      # 150 sqm -> 60 seats (incl. kitchen/back-of-house)

# Capacity: lunch 1.0 turn, dinner 1.2 turns, 26 trading days, 85% practical max fill.
LUNCH_TURNS, DINNER_TURNS = 1.0, 1.2
TRADING_DAYS_PER_MONTH = 26
MAX_PRACTICAL_FILL = 0.85

# Core team (chef + manager, 2 FTE incl. Spanish SS burden) is fixed;
# floor and kitchen staff scale with covers. Lands total labour at
# ~28-36% of revenue at healthy volumes (Hosteleria de Espana 2024).
FIXED_LABOUR_EUR_MO = 5_550
LABOUR_EUR_PER_COVER = 3.4

# Fixed OpEx: SGAE/AGEDI, residuos, insurance, POS, software, licence
# amortisation, cleaning contract. Scales mildly with size.
FIXED_OTHER_EUR_MO_PER_SQM = 12.0       # 150 sqm -> 1,800 EUR/mo

FOOD_COST_RATIO = 0.30

# Demand.
RESIDENT_CAPTURE_RATE = 0.025
RESIDENT_VISITS_PER_MONTH = 2.5
VISITOR_CAPTURE_RATE = 0.012
CATCHMENT_KM2 = 3.14                    # 1 km disc around the hex centre
ADULT_SHARE = 0.75
VISITOR_COVERS_PER_HOTEL = 2_100        # ~100 beds x 70% occ. x 30 days x dining-out share
VISITOR_COVERS_PER_TOURISM_POI = 320
COMPETITION_ELASTICITY = 0.15

# Capex: reforma + extraccion + licensing (~1,067 EUR/sqm) plus a
# rent-indexed fit-out premium (prime locations demand better finishes).
# 150 sqm at 78 EUR/sqm rent -> ~254k EUR; industry range 150-350k.
BASE_CAPEX_EUR_PER_SQM = 160_000 / REFERENCE_SIZE_SQM
FIT_OUT_EUR_PER_SQM_PER_RENT_EUR = 8.0

# Payback is only reported when store EBITDA ("contribution" in column names)
# is credible, and up to 10 years.
MIN_CREDIBLE_CONTRIBUTION_EUR = 2_000
MAX_PAYBACK_MONTHS = 120
# A zone is "viable" only if it pays back within this many months. 24-36
# months is a common operator rule of thumb for casual dining (not a sourced
# benchmark); we use the upper end.
PAYBACK_HURDLE_MONTHS = 36

# Sensitivity scenarios: (rent multiplier, ticket multiplier, capture multiplier).
SCENARIOS: dict[str, tuple[float, float, float]] = {
    "low":  (1.20, 0.90, 0.70),
    "base": (1.00, 1.00, 1.00),
    "high": (0.80, 1.10, 1.30),
}


def seats_for(size_sqm: float) -> int:
    return int(round(size_sqm / SQM_PER_SEAT))


def _economics(out: pd.DataFrame, cuisine: str, size_sqm: float,
               rent_mult: float, ticket_mult: float, capture_mult: float) -> dict[str, pd.Series]:
    lunch_ticket, dinner_ticket = tickets(cuisine)
    lunch_ticket *= ticket_mult
    dinner_ticket *= ticket_mult
    ds = day_share(cuisine)

    adult_residents = out["population_density"].clip(lower=0) * CATCHMENT_KM2 * ADULT_SHARE
    resident_demand = adult_residents * RESIDENT_CAPTURE_RATE * RESIDENT_VISITS_PER_MONTH
    visitor_opps = (
        out["hotel_catchment"] * VISITOR_COVERS_PER_HOTEL
        + out["tourism_catchment"] * VISITOR_COVERS_PER_TOURISM_POI
    )
    visitor_demand = visitor_opps * VISITOR_CAPTURE_RATE
    share = 1.0 / (1.0 + COMPETITION_ELASTICITY * out["same_cuisine_ring"].clip(lower=0))
    demand = (resident_demand + visitor_demand) * share * capture_mult

    seats = seats_for(size_sqm)
    capacity = seats * (LUNCH_TURNS + DINNER_TURNS) * TRADING_DAYS_PER_MONTH * MAX_PRACTICAL_FILL
    covers = demand.clip(upper=capacity)

    revenue = covers * (ds * lunch_ticket + (1 - ds) * dinner_ticket)
    nominal_ticket = ds * lunch_ticket + (1 - ds) * dinner_ticket
    blended_ticket = pd.Series(nominal_ticket, index=out.index)

    rent = out["est_rent_eur_sqm"] * size_sqm * rent_mult
    fixed_other = FIXED_OTHER_EUR_MO_PER_SQM * size_sqm
    fixed_total = rent + FIXED_LABOUR_EUR_MO + fixed_other
    labour = FIXED_LABOUR_EUR_MO + LABOUR_EUR_PER_COVER * covers
    food = revenue * FOOD_COST_RATIO
    contribution = revenue - rent - labour - fixed_other - food

    # Break-even covers: fixed costs / margin per cover. Ticket never 0
    # (nominal ticket used even when demand is zero).
    margin_per_cover = (blended_ticket * (1 - FOOD_COST_RATIO) - LABOUR_EUR_PER_COVER).clip(lower=1.0)
    breakeven = fixed_total / margin_per_cover

    capex = size_sqm * (BASE_CAPEX_EUR_PER_SQM
                        + FIT_OUT_EUR_PER_SQM_PER_RENT_EUR * out["est_rent_eur_sqm"])
    payback = pd.Series(
        [c / m if (m > MIN_CREDIBLE_CONTRIBUTION_EUR and c / m <= MAX_PAYBACK_MONTHS) else math.inf
         for c, m in zip(capex, contribution)],
        index=out.index,
    )
    return {
        "demand": demand, "covers": covers, "capacity": pd.Series(capacity, index=out.index),
        "revenue": revenue, "blended_ticket": blended_ticket, "rent": rent,
        "labour": labour, "food": food, "fixed_other": pd.Series(fixed_other, index=out.index),
        "contribution": contribution, "breakeven": breakeven, "capex": capex,
        "payback": payback, "lunch_covers": covers * ds, "dinner_covers": covers * (1 - ds),
        "competition_share": share,
    }


def compute(df: pd.DataFrame, cuisine: str, city: str = "",
            size_sqm: float = REFERENCE_SIZE_SQM, budget: str | None = None) -> pd.DataFrame:
    """Return a copy with monthly unit economics, capex, payback, sensitivity and risk flags.

    Expects the output of `engine.score_hexes` (needs same_cuisine_ring,
    est_rent_eur_sqm, population_density, hotel, tourism). `budget` (low /
    medium / high) is the most rent per m² the operator would pay: zones above
    it are marked `over_budget` and cannot rank as viable.
    """
    size_sqm = float(min(max(size_sqm, MIN_SIZE_SQM), MAX_SIZE_SQM))
    out = df.copy()
    if out.empty:
        return out
    out["hotel_catchment"] = ring_sum(out, "hotel", w=1.0)
    out["tourism_catchment"] = ring_sum(out, "tourism", w=1.0)
    if "same_cuisine_ring" not in out.columns:
        out["same_cuisine_ring"] = ring_sum(out, "same_cuisine", w=0.5)

    base = _economics(out, cuisine, size_sqm, *SCENARIOS["base"])
    low = _economics(out, cuisine, size_sqm, *SCENARIOS["low"])
    high = _economics(out, cuisine, size_sqm, *SCENARIOS["high"])

    out["size_sqm"]                   = size_sqm
    out["seats"]                      = seats_for(size_sqm)
    out["competition_share"]          = base["competition_share"].round(3)
    out["capacity_capped"]            = base["demand"] > base["capacity"]
    out["monthly_revenue_eur"]        = base["revenue"].round(0)
    out["monthly_rent_eur"]           = base["rent"].round(0)
    out["monthly_food_eur"]           = base["food"].round(0)
    out["monthly_labour_eur"]         = base["labour"].round(0)
    out["monthly_other_eur"]          = base["fixed_other"].round(0)
    out["monthly_contribution_eur"]   = base["contribution"].round(0)
    out["breakeven_covers_per_month"] = base["breakeven"].round(0)
    out["projected_covers_per_month"] = base["covers"].round(0)
    out["lunch_covers_per_month"]     = base["lunch_covers"].round(0)
    out["dinner_covers_per_month"]    = base["dinner_covers"].round(0)
    out["blended_ticket_eur"]         = base["blended_ticket"].round(2)
    out["capex_eur"]                  = base["capex"].round(0)
    out["payback_months"]             = base["payback"].round(1)
    out["contribution_low_eur"]       = low["contribution"].round(0)
    out["contribution_high_eur"]      = high["contribution"].round(0)
    out["payback_low_months"]         = low["payback"].round(1)
    out["payback_high_months"]        = high["payback"].round(1)
    out["concept_feasible"]           = base["covers"] > base["breakeven"]
    cap = BUDGET_MAX_RENT.get(budget) if budget else None
    out["rent_budget_eur_sqm"]        = cap
    out["over_budget"]                = (out["est_rent_eur_sqm"] > cap) if cap else False

    out["risk_flags"] = [_risk_flags(r, city) for _, r in out.iterrows()]
    return out


def _risk_flags(row: pd.Series, city: str) -> list[str]:
    flags: list[str] = []
    c = CITIES.get(city.lower()) if city else None
    if c is not None and row.get("neighbourhood", "") in c.licence_restricted:
        flags.append("licence/BIC proximity — verify sub-barrio")
    if row.get("same_cuisine", 0) >= 4:
        flags.append("high same-cuisine saturation")
    if row.get("crime_per_1000", 0) > 100:
        flags.append("elevated crime")
    if row.get("est_rent_eur_sqm", 0) > 90:
        flags.append("prime-rent corridor")
    if row.get("over_budget", False):
        flags.append("rent above your budget")
    if not row.get("concept_feasible", True):
        flags.append("below break-even")
    if row.get("capacity_capped", False):
        flags.append("demand exceeds seat capacity")
    if row.get("confidence", 1.0) < 0.4:
        flags.append("low data confidence")
    return flags


# --------- Ranking ------------------------------------------------------------

TIER_VIABLE, TIER_SLOW, TIER_OVER_BUDGET, TIER_BELOW_BREAKEVEN, TIER_OUTSKIRTS = 0, 1, 2, 3, 4
TIER_LABELS = {
    TIER_VIABLE: "viable",
    TIER_SLOW: "feasible, slow payback",
    TIER_OVER_BUDGET: "rent above your budget",
    TIER_BELOW_BREAKEVEN: "below break-even",
    TIER_OUTSKIRTS: "outside named neighbourhoods",
}
SHORTLIST_TIERS = (TIER_VIABLE, TIER_SLOW)


def rank_zones(df: pd.DataFrame) -> pd.DataFrame:
    """Add `rank_tier` and `rank` (1 = best). One ranking for map, table and briefs.

    Economics are authoritative; the composite only breaks ties:
      0 viable           feasible, within budget, payback <= 36 months  -> payback asc
      1 slow payback     feasible, within budget, payback > 36 months    -> store EBITDA desc
      2 over budget      feasible, but rent above the budget tier        -> store EBITDA desc
      3 below break-even                                                 -> composite desc
      4 Outskirts        outside the named neighbourhoods                -> composite desc
    """
    out = df.copy()
    if out.empty:
        out["rank_tier"] = pd.Series(dtype=int)
        out["rank"] = pd.Series(dtype=int)
        return out
    named = out.get("neighbourhood", pd.Series("", index=out.index)) != OUTSKIRTS
    feasible = out["concept_feasible"].astype(bool)
    over = (out["over_budget"] if "over_budget" in out.columns
            else pd.Series(False, index=out.index)).astype(bool)
    pb_raw = out["payback_months"].astype(float)
    within_hurdle = np.isfinite(pb_raw) & (pb_raw <= PAYBACK_HURDLE_MONTHS)
    tier = np.select(
        [named & feasible & ~over & within_hurdle, named & feasible & ~over,
         named & feasible & over, named],
        [TIER_VIABLE, TIER_SLOW, TIER_OVER_BUDGET, TIER_BELOW_BREAKEVEN],
        default=TIER_OUTSKIRTS,
    )
    out["rank_tier"] = tier.astype(int)
    pb = pb_raw.where(np.isfinite(pb_raw), 1e9)
    out = out.assign(_pb=pb, _neg_cont=-out["monthly_contribution_eur"],
                     _neg_comp=-out["composite"])
    out["_k2"] = np.where(out["rank_tier"] == TIER_VIABLE, out["_pb"],
                          np.where(out["rank_tier"].isin([TIER_SLOW, TIER_OVER_BUDGET]),
                                   out["_neg_cont"], out["_neg_comp"]))
    out = out.sort_values(["rank_tier", "_k2", "_neg_comp"], kind="mergesort")
    out["rank"] = np.arange(1, len(out) + 1)
    return out.drop(columns=["_pb", "_neg_cont", "_neg_comp", "_k2"]).sort_index()


# --------- Narrative ---------------------------------------------------------


def _f(x, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if not math.isnan(v) else default


def deal_brief(row: pd.Series, cuisine: str, city: str, verdicts_allowed: bool = True) -> str:
    """One-paragraph deal brief with hard numbers and a sensitivity range.

    When `verdicts_allowed` is False (core data is synthetic or estimated)
    the brief states the numbers but gives no go/no-go verdict.
    Risk flags are rendered separately by the UI.
    """
    hood = row.get("neighbourhood", "this zone")
    size = _f(row.get("size_sqm"), REFERENCE_SIZE_SQM)
    rev = _f(row.get("monthly_revenue_eur"))
    cont = _f(row.get("monthly_contribution_eur"))
    rent = _f(row.get("monthly_rent_eur"))
    covers = _f(row.get("projected_covers_per_month"))
    be = _f(row.get("breakeven_covers_per_month"))
    capex = _f(row.get("capex_eur"))
    pb = _f(row.get("payback_months"), math.inf)
    pb_low = _f(row.get("payback_low_months"), math.inf)
    pb_high = _f(row.get("payback_high_months"), math.inf)
    c_low = _f(row.get("contribution_low_eur"), cont)
    c_high = _f(row.get("contribution_high_eur"), cont)
    margin = cont / rev if rev > 0 else 0.0
    feasible = bool(row.get("concept_feasible", False))

    text = (
        f"**{hood}** ({city.title()}) scores {_f(row.get('composite')):.1f}/100 for {cuisine}. "
        f"A {num(size)} sqm concept projects {eur(rev)}/month revenue "
        f"({num(covers)} covers at a {eur(_f(row.get('blended_ticket_eur')), 1)} blended ticket), "
        f"{eur(rent)}/month rent and {eur(cont)}/month store EBITDA ({pct(margin, 1)} margin). "
        f"Capex {eur_k(capex)}, payback {months(pb)}, break-even {num(be)} covers/month. "
        f"Downside case (rent +20%, ticket -10%, demand -30%): {eur(c_low)}/month, "
        f"payback {months(pb_low)}. Upside case: {eur(c_high)}/month, payback {months(pb_high)}."
    )
    if not verdicts_allowed:
        return text + " _No verdict: core data for this city is synthetic or estimated._"

    hurdle = PAYBACK_HURDLE_MONTHS
    within = math.isfinite(pb) and pb <= hurdle
    if not feasible:
        verdict = ("below break-even — a dine-in concept here would need a delivery leg "
                   "or private-events overlay to work")
    elif bool(row.get("over_budget", False)):
        verdict = (f"rent ({eur(_f(row.get('est_rent_eur_sqm')))}/m²) is above your budget of "
                   f"{eur(_f(row.get('rent_budget_eur_sqm')))}/m²; only worth it with a lower rent")
    elif within and math.isfinite(pb_low) and pb_low <= hurdle:
        verdict = (f"strong candidate: payback {months(pb)}, and still within {hurdle} months "
                   "in the downside case")
    elif within:
        verdict = (f"promising ({months(pb)} payback) but the downside case misses the "
                   f"{hurdle}-month hurdle; negotiate rent")
    elif math.isfinite(pb):
        verdict = f"slow: payback {months(pb)}, above the {hurdle}-month hurdle"
    elif margin > 0.08:
        verdict = f"healthy margin but {NO_PAYBACK.lower()}"
    else:
        verdict = "tight margin; only with a higher ticket or lower rent"
    if feasible and bool(row.get("capacity_capped", False)):
        verdict += (" (caution: estimated demand exceeds seat capacity, so revenue assumes a "
                    "near-full room every day; validate footfall on site)")
    return text + f" Verdict: {verdict}."
