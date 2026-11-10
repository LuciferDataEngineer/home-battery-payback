"""Postcode to state.

Australia Post postcode ranges, which the CER postcode file does not include a state column for.
A handful of postcodes cross a state border (notably 0872). Those are assigned to the range owner.
The national battery total still matches the CER state table exactly; state totals differ by
a few dozen systems. See the reconciliation in analytics.
"""

from __future__ import annotations


def normalise_postcode(value: object) -> str | None:
    text = str(value).strip()
    if text.upper().startswith("POA"):
        text = text[3:]
    if not text.isdigit():
        return None
    return text.zfill(4)


def state_of_postcode(postcode: str) -> str | None:
    number = int(postcode)
    if 800 <= number <= 899:
        return "NT"
    if 200 <= number <= 299 or 2600 <= number <= 2618 or 2900 <= number <= 2920:
        return "ACT"
    if 1000 <= number <= 2599 or 2619 <= number <= 2899 or 2921 <= number <= 2999:
        return "NSW"
    if 3000 <= number <= 3999 or 8000 <= number <= 8999:
        return "VIC"
    if 4000 <= number <= 4999 or 9000 <= number <= 9999:
        return "QLD"
    if 5000 <= number <= 5999:
        return "SA"
    if 6000 <= number <= 6999:
        return "WA"
    if 7000 <= number <= 7999:
        return "TAS"
    return None
