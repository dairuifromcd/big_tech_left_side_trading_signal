"""Bounded US cash-equity regular-session calendar, with no third-party packages.

This is an explicit exchange-published 2024--2028 schedule, not a generic US
federal-holiday approximation. Dates outside the verified table fail closed.
Unexpected future exchange closures require an explicit schedule update.
"""

import datetime as dt
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")
CALENDAR_VERSION = "us-cash-equities-2024-2028-verified-2026-10-30"
VERIFIED_AS_OF = "2026-10-30"
FIRST_DATE = dt.date(2024, 1, 1)
LAST_DATE = dt.date(2028, 12, 31)
SOURCES = (
    "https://ir.theice.com/press/news-details/2023/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar/default.aspx",
    "https://www.nyse.com/trade/hours-calendars",
    "https://www.nasdaq.com/market-activity/stock-market-holiday-schedule",
    "https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-announces-closure-its-us-markets-honor-national-day-0",
)

# All full-day closures published in the sources above, including the
# extraordinary 2025-01-09 national day of mourning for President Carter.
_HOLIDAY_TEXT = {
    2024: "01-01 01-15 02-19 03-29 05-27 06-19 07-04 09-02 11-28 12-25",
    2025: "01-01 01-09 01-20 02-17 04-18 05-26 06-19 07-04 09-01 11-27 12-25",
    2026: "01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25",
    2027: "01-01 01-18 02-15 03-26 05-31 06-18 07-05 09-06 11-25 12-24",
    # NYSE explicitly says Jan 1, 2028 (Saturday) has no observed holiday.
    # Therefore Dec 31, 2027 remains a regular session.
    2028: "01-17 02-21 04-14 05-29 06-19 07-04 09-04 11-23 12-25",
}
_EARLY_CLOSE_TEXT = {
    2024: "07-03 11-29 12-24",
    2025: "07-03 11-28 12-24",
    2026: "11-27 12-24",
    2027: "11-26",
    2028: "07-03 11-24",
}
HOLIDAYS = frozenset(
    dt.date.fromisoformat(f"{year}-{month_day}")
    for year, values in _HOLIDAY_TEXT.items() for month_day in values.split()
)
EARLY_CLOSE_DATES = frozenset(
    dt.date.fromisoformat(f"{year}-{month_day}")
    for year, values in _EARLY_CLOSE_TEXT.items() for month_day in values.split()
)


class CalendarError(ValueError):
    """No reliable session answer is available under the verified calendar."""


def _check_date(day):
    if not isinstance(day, dt.date) or isinstance(day, dt.datetime):
        raise CalendarError("Calendar input must be a date, not a datetime.")
    if not FIRST_DATE <= day <= LAST_DATE:
        raise CalendarError(
            f"Calendar supports {FIRST_DATE} through {LAST_DATE}; requested {day}."
        )


def session_bounds(day):
    """Return aware New York (regular open, regular close), or None if closed."""
    _check_date(day)
    if day.weekday() >= 5 or day in HOLIDAYS:
        return None
    close_hour = 13 if day in EARLY_CLOSE_DATES else 16
    return (
        dt.datetime.combine(day, dt.time(9, 30), NY),
        dt.datetime.combine(day, dt.time(close_hour), NY),
    )


def latest_completed_session(now_aware):
    """Latest session whose regular close has actually occurred at `now_aware`.

    The close instant is inclusive: at 16:00 ET (13:00 on published half-days)
    that session is complete; provider publication delay is a separate issue.
    """
    if not isinstance(now_aware, dt.datetime) or now_aware.utcoffset() is None:
        raise CalendarError("An aware datetime is required for a reliable session.")
    local_now = now_aware.astimezone(NY)
    day = local_now.date()
    _check_date(day)
    while day >= FIRST_DATE:
        bounds = session_bounds(day)
        if bounds is not None and local_now >= bounds[1]:
            return day
        day -= dt.timedelta(days=1)
    raise CalendarError("No completed session exists inside the verified calendar.")


def sessions_between(start, end):
    """Return all scheduled regular-session dates, including both endpoints."""
    _check_date(start)
    _check_date(end)
    sessions = []
    day = start
    while day <= end:
        if session_bounds(day) is not None:
            sessions.append(day)
        day += dt.timedelta(days=1)
    return sessions


def calendar_metadata():
    return {
        "version": CALENDAR_VERSION,
        "verified_as_of": VERIFIED_AS_OF,
        "timezone": "America/New_York",
        "supported_first_date": FIRST_DATE.isoformat(),
        "supported_last_date": LAST_DATE.isoformat(),
        "regular_session": "09:30-16:00 America/New_York; published early closes at 13:00",
        "sources": list(SOURCES),
        "method": "Explicit exchange-published holidays and early closes; aware session-close comparison.",
        "limitations": [
            "Dates outside the verified table fail closed with CalendarError.",
            "Unexpected exchange closures after the verification date require a calendar update; no live emergency-closure feed is queried.",
            "Session completion does not guarantee the data provider has published the final daily bar.",
        ],
    }
