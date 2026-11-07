"""Offline contract tests. No DNS or Yahoo requests are made by this module."""

import contextlib
import copy
import datetime as dt
import errno
import io
import json
from pathlib import Path
import socket
import ssl
import tempfile
import unittest
from unittest.mock import patch

import market_calendar as calendar
import test_yahoo_nine as diagnostic


AS_OF = dt.datetime(2026, 10, 30, 12, tzinfo=dt.timezone.utc)
SYMBOLS = [symbol for batch in diagnostic.BATCHES for symbol in batch]


def payload_for(symbol, as_of=AS_OF):
    """Build complete synthetic exchange-session rows, never downloaded data."""
    expected = calendar.latest_completed_session(as_of)
    first = diagnostic.SPCX_IPO_DATE if symbol == "SPCX" else dt.date(2024, 10, 30)
    dates = calendar.sessions_between(first, expected)
    meta = {
        "symbol": symbol,
        "longName": diagnostic.NAME_ALIASES[symbol][0],
        "instrumentType": "EQUITY",
        "exchangeName": "NMS",
        "fullExchangeName": "NasdaqGS",
        "currency": "USD",
        "exchangeTimezoneName": "America/New_York",
    }
    if symbol == "SPCX":
        meta["firstTradeDate"] = int(calendar.session_bounds(first)[0].timestamp())
    return {"chart": {"error": None, "result": [{
        "meta": meta,
        "timestamp": [int(calendar.session_bounds(day)[0].timestamp()) for day in dates],
        "indicators": {
            "adjclose": [{"adjclose": [100.0 + index / 100 for index in range(len(dates))]}],
            "quote": [{"close": [101.0 + index / 100 for index in range(len(dates))]}],
        },
    }]}}


def analyze(symbol="NVDA", payload=None, as_of=AS_OF):
    row = diagnostic.new_row(symbol, 1 if symbol != "SPCX" else 2)
    evidence = diagnostic.analyze_payload(row, payload or payload_for(symbol, as_of), as_of)
    return row, evidence


class FakeClock:
    def __init__(self):
        self.elapsed = 0.0
        self.sleep_calls = []

    def monotonic(self):
        return 1000.0 + self.elapsed

    def sleep(self, seconds):
        if seconds < 0:
            raise AssertionError("A negative sleep was requested")
        self.sleep_calls.append(seconds)
        self.elapsed += seconds

    def utc_now(self):
        return AS_OF + dt.timedelta(seconds=self.elapsed)


class FakeResponse:
    def __init__(self, symbol, status, overrides):
        self.status = status
        self.reason = {200: "OK", 429: "Too Many Requests", 401: "Unauthorized", 403: "Forbidden"}.get(status, "Error")
        self.body = overrides.get(symbol, json.dumps(payload_for(symbol)).encode())

    def getheader(self, key):
        return "120" if key == "Retry-After" and self.status == 429 else None

    def read(self):
        return self.body


@contextlib.contextmanager
def fake_network(statuses=None, overrides=None):
    """Patch every outbound path and advance a fake real-time clock."""
    statuses = statuses or {}
    overrides = overrides or {}
    clock = FakeClock()
    calls = []

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            self.symbol = None

        def request(self, method, target, **kwargs):
            self.symbol = target.split("/chart/", 1)[1].split("?", 1)[0]
            calls.append({"symbol": self.symbol, "method": method, "start": clock.monotonic()})
            clock.elapsed += 1.25

        def getresponse(self):
            return FakeResponse(self.symbol, statuses.get(self.symbol, 200), overrides)

        def close(self):
            pass

    records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))]
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(diagnostic.socket, "getaddrinfo", return_value=records))
        stack.enter_context(patch.object(diagnostic.http.client, "HTTPSConnection", FakeConnection))
        stack.enter_context(patch.object(diagnostic.ssl, "create_default_context", return_value=object()))
        stack.enter_context(patch.object(diagnostic.time, "monotonic", clock.monotonic))
        stack.enter_context(patch.object(diagnostic.time, "sleep", clock.sleep))
        stack.enter_context(patch.object(diagnostic, "utc_now", clock.utc_now))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        yield clock, calls


class PayloadValidationTests(unittest.TestCase):
    def test_complete_history_and_separate_price_evidence(self):
        row, evidence = analyze()
        self.assertTrue(row["data_quality_pass"], row["errors"])
        self.assertTrue(row["indicator_history_ready"])
        self.assertGreaterEqual(row["valid_adjclose_count"], 252)
        self.assertEqual(row["latest_trading_date"], "2026-10-29")
        self.assertEqual(row["missing_count"], 0)
        self.assertEqual(row["duplicate_count"], 0)
        self.assertEqual(len(evidence["rows"]), row["valid_adjclose_count"])
        self.assertIn("timestamp", evidence["rows"][0])
        self.assertIn("close", evidence["rows"][0])
        self.assertIn("adjclose", evidence["rows"][0])
        self.assertNotIn("rows", row)

    def test_spcx_independently_verified_short_ipo_history_passes(self):
        row, _ = analyze("SPCX")
        self.assertTrue(row["identity_validated"], row["errors"])
        self.assertTrue(row["data_quality_pass"], row["errors"])
        self.assertLess(row["valid_adjclose_count"], 252)
        self.assertEqual(row["earliest_trading_date"], "2026-06-12")
        self.assertEqual(row["history_status"], "EXPECTED_SHORT_IPO_HISTORY")
        self.assertFalse(row["indicator_history_ready"])

    def test_spcx_etf_identity_is_rejected(self):
        payload = payload_for("SPCX")
        payload["chart"]["result"][0]["meta"].update({
            "longName": "The SPAC and New Issue ETF", "instrumentType": "ETF",
            "exchangeName": "PCX", "fullExchangeName": "NYSEArca",
        })
        row, _ = analyze("SPCX", payload)
        self.assertEqual(row["error_category"], "IDENTITY_MISMATCH")
        self.assertFalse(row["identity_validated"])
        self.assertEqual(row["valid_adjclose_count"], 0)
        self.assertGreater(row["observed_complete_adjclose_count"], 0)

    def test_spcx_pre_ipo_history_is_identity_contamination(self):
        payload = payload_for("SPCX")
        result = payload["chart"]["result"][0]
        result["timestamp"].insert(0, int(calendar.session_bounds(dt.date(2026, 6, 11))[0].timestamp()))
        result["indicators"]["adjclose"][0]["adjclose"].insert(0, 100.0)
        result["indicators"]["quote"][0]["close"].insert(0, 100.0)
        row, _ = analyze("SPCX", payload)
        self.assertEqual(row["error_category"], "IDENTITY_MISMATCH")
        self.assertFalse(row["identity_validated"])
        self.assertEqual(row["valid_adjclose_count"], 0)

    def test_spcx_ipo_gap_cannot_be_excused_as_short_listing(self):
        payload = payload_for("SPCX")
        result = payload["chart"]["result"][0]
        for array in (result["timestamp"], result["indicators"]["adjclose"][0]["adjclose"], result["indicators"]["quote"][0]["close"]):
            array.pop(3)
        row, _ = analyze("SPCX", payload)
        self.assertFalse(row["data_quality_pass"])
        self.assertFalse(row["short_history_explained"])
        self.assertEqual(row["missing_expected_session_count"], 1)

    def test_unexplained_short_history_is_not_assumed_new_listing(self):
        payload = payload_for("AAPL")
        result = payload["chart"]["result"][0]
        result["timestamp"] = result["timestamp"][-100:]
        result["indicators"]["adjclose"][0]["adjclose"] = result["indicators"]["adjclose"][0]["adjclose"][-100:]
        result["indicators"]["quote"][0]["close"] = result["indicators"]["quote"][0]["close"][-100:]
        row, _ = analyze("AAPL", payload)
        self.assertFalse(row["short_history_explained"])
        self.assertIn("INSUFFICIENT_HISTORY", {error["category"] for error in row["errors"]})

    def test_missing_adjclose(self):
        payload = payload_for("NVDA")
        del payload["chart"]["result"][0]["indicators"]["adjclose"]
        row, _ = analyze(payload=payload)
        self.assertEqual(row["error_category"], "MISSING_ADJCLOSE")
        self.assertFalse(row["data_quality_pass"])

    def test_bad_prices_are_quality_errors(self):
        for bad in (None, float("nan"), float("inf"), -1, 0, True):
            with self.subTest(bad=bad):
                payload = payload_for("NVDA")
                payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][3] = bad
                row, evidence = analyze(payload=payload)
                self.assertFalse(row["data_quality_pass"])
                self.assertEqual(row["missing_count"], 1)
                self.assertIn("DATA_QUALITY_ERROR", {error["category"] for error in row["errors"]})
                json.dumps(evidence, allow_nan=False)

    def test_close_timestamp_duplicate_and_array_mismatch(self):
        for mutation in ("close", "timestamp", "duplicate", "length"):
            with self.subTest(mutation=mutation):
                payload = payload_for("NVDA")
                result = payload["chart"]["result"][0]
                if mutation == "close":
                    result["indicators"]["quote"][0]["close"][3] = None
                elif mutation == "timestamp":
                    result["timestamp"][3] = None
                elif mutation == "duplicate":
                    result["timestamp"][3] = result["timestamp"][2]
                else:
                    result["indicators"]["quote"][0]["close"].pop()
                row, _ = analyze(payload=payload)
                self.assertFalse(row["data_quality_pass"])
                self.assertIn("DATA_QUALITY_ERROR", {error["category"] for error in row["errors"]})

    def test_latest_missing_session_is_stale(self):
        payload = payload_for("NVDA")
        result = payload["chart"]["result"][0]
        for array in (result["timestamp"], result["indicators"]["adjclose"][0]["adjclose"], result["indicators"]["quote"][0]["close"]):
            array.pop()
        row, _ = analyze(payload=payload)
        self.assertIn("STALE_DATA", {error["category"] for error in row["errors"]})
        self.assertFalse(row["data_quality_pass"])

    def test_in_progress_daily_bar_is_excluded(self):
        as_of = dt.datetime(2026, 10, 30, 14, tzinfo=dt.timezone.utc)
        payload = payload_for("NVDA", as_of)
        result = payload["chart"]["result"][0]
        result["timestamp"].append(int(calendar.session_bounds(dt.date(2026, 10, 30))[0].timestamp()))
        result["indicators"]["adjclose"][0]["adjclose"].append(200.0)
        result["indicators"]["quote"][0]["close"].append(200.0)
        row, _ = analyze(payload=payload, as_of=as_of)
        self.assertTrue(row["data_quality_pass"], row["errors"])
        self.assertEqual(row["expected_trading_date"], "2026-10-29")
        self.assertEqual(row["latest_trading_date"], "2026-10-29")
        self.assertEqual(row["latest_returned_trading_date"], "2026-10-30")
        self.assertFalse(row["latest_returned_row_is_completed_regular_session"])
        self.assertEqual(row["incomplete_session_row_count"], 1)

    def test_unsupported_calendar_fails_closed(self):
        row, _ = analyze(payload=payload_for("NVDA"), as_of=dt.datetime(2029, 1, 2, 22, tzinfo=dt.timezone.utc))
        self.assertFalse(row["calendar_validated"])
        self.assertFalse(row["data_quality_pass"])
        self.assertIn("DATA_QUALITY_ERROR", {error["category"] for error in row["errors"]})


class CollectionAndRunnerTests(unittest.TestCase):
    def run_offline(self, directory, statuses=None, overrides=None):
        with fake_network(statuses, overrides) as (clock, calls):
            report = diagnostic.run(directory, "offline-unittest")
        return report, clock, calls

    def test_all_nine_serial_schedule_and_atomic_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            report, clock, calls = self.run_offline(directory)
            self.assertEqual([item["symbol"] for item in calls], SYMBOLS)
            self.assertEqual(report["actual_http_request_count"], 9)
            self.assertEqual(report["http_200_count"], 9)
            self.assertEqual(report["success_count"], 9)
            self.assertEqual(report["failure_count"], 0)
            self.assertEqual(report["batch_extra_wait_count"], 2)
            self.assertTrue(report["timing_pass"])
            self.assertTrue(report["all_nine_have_explicit_results"])
            self.assertFalse(report["rate_limited"])
            for interval in report["request_intervals"]:
                minimum = 35.0 if interval["batch_boundary"] else 5.0
                self.assertGreaterEqual(interval["start_gap_seconds"], minimum)
                if interval["batch_boundary"]:
                    self.assertGreaterEqual(interval["batch_extra_wait_seconds"], 30.0)
            self.assertEqual(clock.sleep_calls.count(30.0), 2)
            stored = json.loads(Path(report["report_file"]).read_text())
            evidence = json.loads(Path(report["price_evidence_file"]).read_text())
            self.assertEqual(stored["success_count"], 9)
            self.assertEqual(len(evidence["stocks"]), 9)
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_429_stops_immediately_and_marks_remaining_six(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _, calls = self.run_offline(directory, {"GOOGL": 429})
        self.assertEqual([item["symbol"] for item in calls], SYMBOLS[:3])
        self.assertEqual(report["actual_http_request_count"], 3)
        self.assertTrue(report["rate_limited"])
        self.assertEqual(report["overall_conclusion"], "RATE_LIMITED")
        self.assertEqual(report["stocks"][2]["retry_after"], "120")
        self.assertEqual(report["stocks"][2]["error_category"], "RATE_LIMITED")
        self.assertEqual(report["skipped_count"], 6)
        self.assertTrue(report["all_nine_have_explicit_results"])
        self.assertTrue(all(row["status"] == "SKIPPED_RATE_LIMITED" for row in report["stocks"][3:]))

    def test_one_401_continues_but_consecutive_401_403_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _, calls = self.run_offline(directory, {"NVDA": 401})
        self.assertEqual(len(calls), 9)
        self.assertEqual(report["stocks"][0]["error_category"], "HTTP_UNAUTHORIZED")
        with tempfile.TemporaryDirectory() as directory:
            report, _, calls = self.run_offline(directory, {"NVDA": 401, "AAPL": 403})
        self.assertEqual(len(calls), 2)
        self.assertEqual(report["stocks"][1]["error_category"], "HTTP_FORBIDDEN")
        self.assertEqual(report["skipped_count"], 7)

    def test_invalid_json_fails_one_stock_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _, calls = self.run_offline(directory, overrides={"NVDA": b"not-json"})
        self.assertEqual(len(calls), 9)
        self.assertEqual(report["stocks"][0]["error_category"], "INVALID_JSON")
        self.assertEqual(sum(item["symbol"] == "NVDA" for item in calls), 1)

    def test_dns_failure_has_zero_http_invocations(self):
        row = diagnostic.new_row("NVDA", 1)
        with patch.object(diagnostic.socket, "getaddrinfo", side_effect=socket.gaierror(-2, "mock resolver failure")), patch.object(diagnostic.http.client, "HTTPSConnection") as connection:
            diagnostic.collect_symbol(row, diagnostic.RequestScheduler())
        connection.assert_not_called()
        self.assertEqual(row["http_request_count"], 0)
        self.assertEqual(row["error_category"], "DNS_ERROR")

    def test_network_exception_classification_prioritizes_ssl(self):
        cases = (
            (ssl.SSLCertVerificationError(1, "mock certificate failure"), "TLS_ERROR"),
            (PermissionError(errno.EPERM, "mock permission denial"), "CONNECTION_ERROR"),
            (ConnectionRefusedError(errno.ECONNREFUSED, "mock refusal"), "CONNECTION_ERROR"),
            (TimeoutError("mock timeout"), "TIMEOUT"),
            (socket.gaierror(-2, "mock DNS failure"), "DNS_ERROR"),
        )
        for exc, expected in cases:
            with self.subTest(exception=type(exc).__name__):
                row = diagnostic.new_row("NVDA", 1)
                diagnostic.network_error(row, exc, "HTTPS")
                self.assertEqual(row["error_category"], expected)
                self.assertEqual(row["errors"][0]["local_permission_denied"], isinstance(exc, PermissionError))


if __name__ == "__main__":
    unittest.main()
