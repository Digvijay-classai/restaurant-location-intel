"""Spanish (es-ES) number and currency formatting for UI copy."""
from __future__ import annotations

import math

NO_PAYBACK = "No payback within 10 yrs"


def _group(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def num(x: float | None, decimals: int = 0) -> str:
    """12345.6 -> '12.346'; 3.14159 with decimals=1 -> '3,1'. NaN/None -> '—'."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    if decimals == 0:
        return _group(int(round(x)))
    whole, frac = f"{abs(x):.{decimals}f}".split(".")
    sign = "-" if x < 0 else ""
    return f"{sign}{_group(int(whole))},{frac}"


def eur(x: float | None, decimals: int = 0) -> str:
    """12345 -> '12.345 €'."""
    s = num(x, decimals)
    return s if s == "—" else f"{s} €"


def eur_k(x: float | None) -> str:
    """253600 -> '254k €'."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return f"{_group(int(round(x / 1000)))}k €"


def pct(x: float | None, decimals: int = 0) -> str:
    """0.142 -> '14 %' (es-ES puts a space before %)."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return f"{num(x * 100, decimals)} %"


def months(x: float | None) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return NO_PAYBACK
    return f"{int(round(x))} months"
