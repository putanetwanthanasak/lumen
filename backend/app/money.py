"""The one money and rate parser, shared by rules.json and webhooks (L49, review L5).

Money and rates must arrive as JSON strings in a strict plain-decimal form. Anything
else is rejected, never coerced or rounded: a JSON number (it would pass through
float), a sign, whitespace, underscores, an exponent, NaN, non-ASCII digits, or more
places than the column holds. Postgres would silently round 123.455 to 123.46 on
insert (review L3), so the check has to happen here, before Decimal.
"""

import re
from collections.abc import Callable
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator

# [0-9], not \d: \d also matches Thai and other Unicode digits, which Decimal accepts.
# Used with fullmatch, so a trailing newline cannot slip through as it would with $.
# Money: Numeric(12,2) holds 10 integer digits, so every match is below 1E10.
MONEY_PATTERN = re.compile(r"[0-9]{1,10}(\.[0-9]{1,2})?")
# Rates: Numeric(7,6) holds 1 integer digit and 6 places.
RATE_PATTERN = re.compile(r"[0-9](\.[0-9]{1,6})?")


def decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):  # NaN / Infinity have no decimal places
        raise ValueError("must be finite")
    return max(0, -exponent)


def _parser(pattern: re.Pattern[str], example: str, rule: str) -> Callable[[object], Decimal]:
    def parse(value: object) -> Decimal:
        if not isinstance(value, str):
            raise ValueError(
                f'must be a JSON string such as "{example}", got {type(value).__name__}'
            )
        if pattern.fullmatch(value) is None:
            raise ValueError(f'must be a plain decimal string such as "{example}" ({rule})')
        return Decimal(value)

    return parse


parse_money = _parser(MONEY_PATTERN, "1234.50", "at most 2 decimal places, below 1E10")
parse_rate = _parser(RATE_PATTERN, "0.020833", "at most 6 decimal places, below 10")

MoneyStr = Annotated[Decimal, BeforeValidator(parse_money)]
RateStr = Annotated[Decimal, BeforeValidator(parse_rate)]
