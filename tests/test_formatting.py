"""es-ES formatting helpers."""
import math

from src.formatting import NO_PAYBACK, eur, eur_k, months, num, pct


def test_spanish_number_format():
    assert num(1234567) == "1.234.567"
    assert num(3.14159, 1) == "3,1"
    assert num(-1234.5, 1) == "-1.234,5"
    assert eur(12345) == "12.345 €"
    assert eur_k(253_600) == "254k €"
    assert pct(0.142, 1) == "14,2 %"


def test_non_finite_values():
    assert num(math.nan) == "—" and eur(None) == "—"
    assert months(math.inf) == NO_PAYBACK
    assert months(27.4) == "27 months"
