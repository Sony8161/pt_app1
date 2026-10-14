"""Comparing money and hours that arrive as floats."""

from __future__ import annotations


def fits(total: float, limit: float) -> bool:
    """True when ``total`` is within ``limit``, compared to the cent.

    Adding floats lands a hair off (5532.60 + 2324.61 is 7857.209999999999, which is not <= 7857.21), so a plan that
    uses the whole budget exactly would be refused. Hours get the same two decimals; the database stores both that way.
    """
    return round(total, 2) <= round(limit, 2)
