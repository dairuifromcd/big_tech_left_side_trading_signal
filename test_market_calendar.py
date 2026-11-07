"""Offline regression tests for cash-equity calendar boundaries."""

import datetime as dt
import unittest

from market_calendar import (
    CalendarError, NY, latest_completed_session, session_bounds, sessions_between,
)


class CalendarTests(unittest.TestCase):
    def at(self, text):
        return dt.datetime.fromisoformat(text).replace(tzinfo=NY)

    def test_regular_close_boundary(self):
        self.assertEqual(latest_completed_session(self.at("2026-10-30T15:59:59")), dt.date(2026, 10, 29))
        self.assertEqual(latest_completed_session(self.at("2026-10-30T16:00:00")), dt.date(2026, 10, 30))

    def test_weekend_and_premarket(self):
        self.assertEqual(latest_completed_session(self.at("2026-11-01T18:00:00")), dt.date(2026, 10, 30))
        self.assertEqual(latest_completed_session(self.at("2026-11-02T09:29:59")), dt.date(2026, 10, 30))

    def test_holidays(self):
        self.assertEqual(latest_completed_session(self.at("2026-07-03T18:00:00")), dt.date(2026, 7, 2))
        self.assertEqual(latest_completed_session(self.at("2026-04-03T18:00:00")), dt.date(2026, 4, 2))
        self.assertIsNone(session_bounds(dt.date(2025, 1, 9)))

    def test_early_close(self):
        self.assertEqual(latest_completed_session(self.at("2026-11-27T12:59:59")), dt.date(2026, 11, 25))
        self.assertEqual(latest_completed_session(self.at("2026-11-27T13:00:00")), dt.date(2026, 11, 27))
        self.assertEqual(session_bounds(dt.date(2026, 12, 24))[1].hour, 13)

    def test_dst_changes_utc_close(self):
        winter = session_bounds(dt.date(2026, 1, 2))[1].astimezone(dt.timezone.utc)
        summer = session_bounds(dt.date(2026, 7, 2))[1].astimezone(dt.timezone.utc)
        self.assertEqual(winter.hour, 21)
        self.assertEqual(summer.hour, 20)
        self.assertEqual(latest_completed_session(dt.datetime(2026, 10, 30, 3, 58, tzinfo=dt.timezone.utc)), dt.date(2026, 10, 29))

    def test_no_observation_for_saturday_new_year_2028(self):
        self.assertIsNotNone(session_bounds(dt.date(2027, 12, 31)))
        self.assertEqual(latest_completed_session(self.at("2028-01-01T12:00:00")), dt.date(2027, 12, 31))

    def test_exact_session_enumeration(self):
        self.assertEqual(sessions_between(dt.date(2025, 1, 8), dt.date(2025, 1, 10)), [dt.date(2025, 1, 8), dt.date(2025, 1, 10)])

    def test_fail_closed(self):
        for day in (dt.date(2023, 12, 31), dt.date(2029, 1, 1)):
            with self.assertRaises(CalendarError):
                session_bounds(day)
        with self.assertRaises(CalendarError):
            latest_completed_session(dt.datetime(2026, 10, 30, 12))
        with self.assertRaises(CalendarError):
            latest_completed_session(self.at("2024-01-01T18:00:00"))


if __name__ == "__main__":
    unittest.main()
