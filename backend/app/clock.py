"""Today's date for the user, as a FastAPI dependency so tests can fix it.

Lumen's users are in Thailand. Asia/Bangkok is UTC+7 all year (no daylight saving),
so a fixed offset gives the same date as the zone database without depending on it.
"""

from datetime import UTC, date, datetime, timedelta, timezone

BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")


def date_in_bangkok(instant: datetime) -> date:
    return instant.astimezone(BANGKOK).date()


def today() -> date:
    return date_in_bangkok(datetime.now(UTC))
