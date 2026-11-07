"""Read-only regression checks for the offline historical-price revision audit.

All inputs are in-memory fixtures or previously saved evidence. Network entry
points are patched to fail immediately; production state and evidence are never
written. Run with PYTHONDONTWRITEBYTECODE=1 python -m unittest
tests.test_revision_diagnostics -v.
"""

import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import market_calendar as calendar
from diagnostics import analyze_adjclose_revisions as audit
from diagnostics.revision_scenarios import run_scenarios


ROOT = Path(__file__).resolve().parents[1]
PHASE2 = ROOT / "reports/yahoo_nine_prices_20261030_141537.json"
_ACCEPTANCE = json.loads((ROOT / "phase4_trial/acceptance.json").read_text())
_LIVE_REPORT = audit.resolve_path(_ACCEPTANCE["live_report"], ROOT)
PHASE4 = audit.resolve_path(json.loads(_LIVE_REPORT.read_text())["input_file"], ROOT, _LIVE_REPORT.parent)
EXPECTED_REVISIONS = {
    "NVDA": 210, "AAPL": 204, "GOOGL": 189, "MSFT": 162,
    "AMZN": 0, "SPCX": 0, "META": 156, "AVGO": 218, "TSLA": 0,
}


def row_for(day, price, close=None, minute=30):
    day = dt.date.fromisoformat(day) if isinstance(day, str) else day
    instant = dt.datetime.combine(day, dt.time(9, minute), calendar.NY)
    return {
        "timestamp": int(instant.timestamp()),
        "trading_date": day.isoformat(),
        "adjclose": price,
        "close": price if close is None else close,
        "regular_session_completed": True,
        "flags": [],
    }


def fixture_rows(prices, end="2026-10-29"):
    days = calendar.sessions_between(dt.date(2025, 1, 1), dt.date.fromisoformat(end))[-len(prices):]
    if len(days) != len(prices):
        raise AssertionError("Fixture does not have enough calendar sessions")
    return [row_for(day, price) for day, price in zip(days, prices)]


class OfflineOnlyTestCase(unittest.TestCase):
    """Any accidental DNS or outbound connection fails the test immediately."""
    def setUp(self):
        for target in ("socket.getaddrinfo", "socket.create_connection",
                       "http.client.HTTPConnection.connect", "http.client.HTTPSConnection.connect"):
            blocker = patch(target, side_effect=AssertionError("Offline audit attempted network access"))
            blocker.start()
            self.addCleanup(blocker.stop)


class IndexAndStatisticsTests(OfflineOnlyTestCase):
    def test_equal_and_reordered_rows_align_by_date_without_mutation(self):
        old = fixture_rows([100.0, 101.0, 102.0])
        new = list(reversed(copy.deepcopy(old)))
        before = copy.deepcopy((old, new))
        result = audit.compare_rows(old, new)
        self.assertEqual(result["overlap_count"], 3)
        self.assertEqual(result["exact_equal_count"], 3)
        self.assertEqual(result["raw_different_count"], 0)
        self.assertEqual(result["revision_count"], 0)
        self.assertEqual(result["max_abs_diff"], 0)
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["top5"], [])
        self.assertEqual((old, new), before)

    def test_ny_dst_timestamp_alignment(self):
        rows = [row_for("2026-03-06", 100.0), row_for("2026-03-09", 101.0)]
        self.assertEqual(dt.datetime.fromtimestamp(rows[0]["timestamp"], dt.timezone.utc).hour, 14)
        self.assertEqual(dt.datetime.fromtimestamp(rows[1]["timestamp"], dt.timezone.utc).hour, 13)
        self.assertEqual(sorted(audit.index_rows(list(reversed(rows)))), ["2026-03-06", "2026-03-09"])

    def test_duplicate_and_saved_date_mismatch_fail(self):
        first = row_for("2026-10-29", 100.0)
        duplicate = row_for("2026-10-29", 101.0, minute=31)
        with self.assertRaises(audit.EvidenceError):
            audit.index_rows([first, duplicate])
        mismatch = dict(first, trading_date="2026-10-28")
        with self.assertRaises(audit.EvidenceError):
            audit.index_rows([mismatch])

    def test_invalid_prices_and_timestamps_fail_before_comparison(self):
        for field in ("adjclose", "close"):
            for value in (None, True, 0, -1, float("nan"), float("inf"), "100"):
                with self.subTest(field=field, value=value):
                    row = row_for("2026-10-29", 100.0)
                    row[field] = value
                    with self.assertRaises(audit.EvidenceError):
                        audit.index_rows([row])
        for value in (None, True, "invalid", float("nan"), float("inf"), 1e300):
            with self.subTest(timestamp=value):
                row = row_for("2026-10-29", 100.0)
                row["timestamp"] = value
                with self.assertRaises(audit.EvidenceError):
                    audit.index_rows([row])

    def test_holiday_and_outside_regular_session_fail(self):
        for day, hour in (("2026-10-29", 8), ("2026-10-31", 10), ("2026-11-26", 10)):
            with self.subTest(day=day, hour=hour):
                row = row_for(day, 100.0)
                row["timestamp"] = int(dt.datetime.combine(dt.date.fromisoformat(day), dt.time(hour), calendar.NY).timestamp())
                with self.assertRaises(audit.EvidenceError):
                    audit.index_rows([row])

    def test_new_and_missing_dates_are_distinct_from_revisions(self):
        old = [row_for("2026-10-27", 100.0), row_for("2026-10-28", 101.0)]
        new = [row_for("2026-10-28", 101.0), row_for("2026-10-29", 102.0)]
        result = audit.compare_rows(old, new)
        self.assertEqual(result["overlap_count"], 1)
        self.assertEqual(result["missing_dates"], ["2026-10-27"])
        self.assertEqual(result["new_dates"], ["2026-10-29"])
        self.assertEqual(result["revision_count"], 0)
        with self.assertRaises(audit.EvidenceError):
            audit.compare_rows(old[:1], new[-1:])

    def test_timestamp_or_close_changes_do_not_become_adjclose_revisions(self):
        old = [row_for("2026-10-29", 100.0, close=101.0)]
        new = [row_for("2026-10-29", 100.0, close=102.0, minute=31)]
        result = audit.compare_rows(old, new)
        self.assertEqual(result["timestamp_different_count"], 1)
        self.assertEqual(result["close_different_count"], 1)
        self.assertEqual(result["raw_different_count"], 0)
        self.assertEqual(result["revision_count"], 0)
        self.assertEqual(len(result["changes"]), 1)
        self.assertEqual(result["changes"][0]["abs_diff"], 0)

    def test_percentile_linear_interpolation(self):
        self.assertIsNone(audit.percentile([], .95))
        self.assertEqual(audit.percentile([7], .95), 7)
        self.assertEqual(audit.percentile([40, 0, 20, 10, 30], .5), 20)
        self.assertEqual(audit.percentile([0, 10, 20, 30, 40], .95), 38)
        for invalid in (-.01, 1.01):
            with self.assertRaises(ValueError):
                audit.percentile([0, 1], invalid)

    def test_difference_bins_quantiles_and_top_five(self):
        deltas = [0, 5e-7, 1e-5, .001, .05, .2]
        old = fixture_rows([1.0] * len(deltas))
        new = copy.deepcopy(old)
        for row, delta in zip(new, deltas):
            row["adjclose"] += delta
        result = audit.compare_rows(old, new)
        self.assertEqual(result["raw_different_count"], 5)
        self.assertEqual(result["absolute_difference_bins"], {
            "le_0.000001": 2, "gt_0.000001_le_0.0001": 1,
            "gt_0.0001_le_0.01": 1, "gt_0.01_le_0.10": 1, "gt_0.10": 1,
        })
        self.assertAlmostEqual(result["max_abs_diff"], .2)
        self.assertAlmostEqual(result["max_rel_diff"], .2)
        self.assertAlmostEqual(result["median_abs_diff_all_overlap"], .000505)
        self.assertAlmostEqual(result["p95_abs_diff_all_overlap"], .1625)
        self.assertAlmostEqual(result["median_abs_diff_changed_only"], .001)
        self.assertAlmostEqual(result["p95_abs_diff_changed_only"], .17)
        self.assertEqual([item["date"] for item in result["top5"]], [row["trading_date"] for row in reversed(new[1:])])

    def test_read_json_rejects_nonfinite_literals_without_writes(self):
        for text in ('{"price":NaN}', '{"price":Infinity}', '{broken'):
            with self.subTest(text=text), patch.object(Path, "is_file", return_value=True), patch.object(Path, "read_text", return_value=text):
                with self.assertRaises(audit.EvidenceError):
                    audit.read_json("in-memory.json")


class ToleranceAndImpactTests(OfflineOnlyTestCase):
    def test_current_tolerance_distinguishes_raw_numeric_difference(self):
        old = fixture_rows([100.0, 100.0])
        new = copy.deepcopy(old)
        new[0]["adjclose"] += 5e-9
        new[1]["adjclose"] += 2e-8
        result = audit.compare_rows(old, new)
        self.assertEqual(audit.current_tolerances(), {"abs_tol": 1e-8, "rel_tol": 1e-10})
        self.assertEqual(result["raw_different_count"], 2)
        self.assertEqual(result["revision_count"], 1)
        self.assertTrue(result["counts_match_production"])

    def test_candidate_tolerances_only_change_classification_not_inputs(self):
        deltas = [0, 5e-9, 5e-7, 5e-5, 5e-4, .002]
        old = fixture_rows([100.0] * len(deltas))
        new = copy.deepcopy(old)
        for row, delta in zip(new, deltas):
            row["adjclose"] += delta
        before = copy.deepcopy((old, new))
        policies = {entry["policy"]: entry for entry in audit.evaluate_tolerances(old, new)}
        self.assertEqual({name: item["revision_count"] for name, item in policies.items()}, {
            "STRICT_EQUAL": 5, "CURRENT": 4, "ABS_1E6": 3,
            "ABS_1E6_REL_1E7": 3, "ABS_1E4": 2,
            "ABS_1E4_REL_1E7": 2, "ABS_1E3_REL_1E6_STRESS": 1,
        })
        self.assertAlmostEqual(policies["ABS_1E4"]["max_ignored_abs_diff"], 5e-5)
        self.assertTrue(all(not item["indicator_values_changed_by_comparison_policy"] for item in policies.values()))
        self.assertTrue(all(not item["watch_tier_changed_by_comparison_policy"] for item in policies.values()))
        self.assertEqual((old, new), before)

    def test_metric_impacts_are_actual_full_precision_differences(self):
        old = fixture_rows([100.0] + [90.0] * 250 + [85.0])
        new = copy.deepcopy(old)
        new[-1]["adjclose"] = 79.0
        before = copy.deepcopy((old, new))
        result = audit.impact(old, new)
        self.assertTrue(result["tier_changed"])
        self.assertEqual(result["phase2"]["watch_tier"], "WATCH_10")
        self.assertEqual(result["phase4"]["watch_tier"], "WATCH_20")
        self.assertAlmostEqual(result["delta"]["drawdown_pp"], -6)
        self.assertAlmostEqual(result["delta"]["sma50"], -6 / 50)
        self.assertAlmostEqual(result["delta"]["sma200"], -6 / 200)
        for key in ("rsi14", "sma50", "sma200"):
            self.assertEqual(result["delta"][key], result["phase4"][key] - result["phase2"][key])
        self.assertTrue(result["observation_scale_exceeded"]["drawdown_pp"])
        self.assertFalse(result["highest_price_changed"])
        self.assertEqual((old, new), before)

    def test_short_history_requires_explicit_permission_and_has_null_sma200(self):
        short = fixture_rows([100.0] * 98)
        with self.assertRaises(ValueError):
            audit.impact(short, short)
        result = audit.impact(short, short, allow_short=True)
        self.assertEqual(result["phase2"]["window_samples"], 98)
        self.assertIsNone(result["phase2"]["sma200"])
        self.assertIsNone(result["delta"]["sma200"])
        self.assertFalse(result["observation_scale_exceeded"]["sma200"])

    def test_future_rows_do_not_change_target_session_metrics(self):
        old = fixture_rows([100.0] + [90.0] * 251)
        new = copy.deepcopy(old) + [row_for("2026-10-30", 900.0)]
        result = audit.impact(old, new, target="2026-10-29")
        self.assertEqual(result["phase2"], result["phase4"])
        self.assertFalse(result["tier_changed"])

    def test_relaxed_tolerance_can_hide_tier_boundary_change(self):
        old = fixture_rows([100.0] + [89.0] * 250 + [90.0])
        new = copy.deepcopy(old)
        new[0]["adjclose"] = 99.99999995
        policies = {entry["policy"]: entry for entry in audit.evaluate_tolerances(old, new)}
        self.assertEqual(policies["CURRENT"]["revision_count"], 1)
        self.assertEqual(policies["ABS_1E6"]["revision_count"], 0)
        self.assertTrue(audit.impact(old, new)["tier_changed"])


class SavedEvidenceAndScenarioTests(OfflineOnlyTestCase):
    def test_all_nine_real_snapshots_reproduce_1139_revisions_read_only(self):
        paths = (PHASE2, PHASE4, ROOT / "state/monitor_state.json", ROOT / "phase4_trial/state/monitor_state.json")
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        old, new = json.loads(PHASE2.read_text()), json.loads(PHASE4.read_text())
        counts = {}
        for symbol, expected_count in EXPECTED_REVISIONS.items():
            with self.subTest(symbol=symbol):
                a = old["stocks"][symbol]["rows"]
                b = new["stocks"][symbol]["rows"]
                result = audit.compare_rows(a, b)
                counts[symbol] = result["revision_count"]
                self.assertEqual(result["revision_count"], expected_count)
                self.assertTrue(result["counts_match_production"])
                self.assertEqual(result["close_different_count"], 0)
                self.assertEqual(result["timestamp_different_count"], 0)
                self.assertEqual(result["missing_date_count"], 0)
                self.assertEqual(result["new_date_count"], 0)
                self.assertEqual(sum(result["absolute_difference_bins"].values()), result["overlap_count"])
                calculated = audit.impact(a, b, allow_short=symbol == "SPCX")
                self.assertFalse(calculated["tier_changed"])
                if symbol == "SPCX":
                    self.assertIsNone(calculated["delta"]["sma200"])
        self.assertEqual(sum(counts.values()), 1139)
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})

    def test_scenarios_a_to_e_expose_suppression_and_idempotence_without_state_write(self):
        formal = ROOT / "state/monitor_state.json"
        old_hash = hashlib.sha256(formal.read_bytes()).hexdigest()
        scenarios = {item["scenario"]: item for item in run_scenarios()}
        self.assertEqual(set(scenarios), set("ABCDE"))
        self.assertTrue(all(item["synthetic"] for item in scenarios.values()))
        self.assertTrue(all(not item["production_logic_modified"] for item in scenarios.values()))
        self.assertTrue(all(not item["safe_to_notify_as_buy_signal"] for item in scenarios.values()))
        self.assertEqual(scenarios["A"]["actual_production_result"]["change_event"], "HISTORICAL_REVISION")
        self.assertEqual(scenarios["A"]["actual_production_result"]["new_thresholds"], [])
        self.assertTrue(scenarios["B"]["signal_suppression_risk"])
        self.assertEqual(scenarios["B"]["unrevised_control_event"], "NEW_THRESHOLD")
        self.assertTrue(scenarios["B"]["suppressed_threshold_marked_triggered"])
        self.assertEqual(scenarios["C"]["old_basis_counterfactual"]["watch_tier"], "WATCH_10")
        self.assertEqual(scenarios["C"]["revised_basis_metrics"]["watch_tier"], "WATCH_20")
        self.assertTrue(scenarios["D"]["requires_review"])
        self.assertFalse(scenarios["D"]["causal_attribution_confirmed"])
        self.assertEqual(scenarios["E"]["actual_production_result"]["change_event"], "NO_CHANGE")
        self.assertEqual(scenarios["E"]["overlap_revision_count"], 0)
        self.assertTrue(scenarios["E"]["history_fingerprint_equal"])
        self.assertFalse(scenarios["E"]["production_monitor_would_write_state"])
        self.assertEqual(old_hash, hashlib.sha256(formal.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
