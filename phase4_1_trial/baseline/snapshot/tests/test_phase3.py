import copy
import datetime as dt
from decimal import Decimal, localcontext
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import market_calendar as calendar
from src import indicators as ind, signals, state, monitor


def series(prices):
    dates = calendar.sessions_between(dt.date(2024, 1, 2), dt.date(2026, 10, 29))[:len(prices)]
    return [(d.isoformat(), p) for d, p in zip(dates, prices)]


def calc(prices):
    rows = series(prices)
    return ind.calculate(rows, rows[-1][0], allow_short=True)


class IndicatorTests(unittest.TestCase):
    def test_normal_drawdown(self):
        self.assertAlmostEqual(calc([100] * 251 + [80])["drawdown"], -.2)

    def test_no_drawdown(self):
        self.assertEqual(calc([100] * 252)["drawdown"], 0)

    def test_new_high(self):
        self.assertEqual(calc([100] * 252 + [120])["highest_adjclose"], 120)

    def test_high_leaves_window(self):
        result = calc([200] + [100] * 251 + [80])
        self.assertEqual(result["window_samples"], 252)
        self.assertEqual(result["highest_adjclose"], 100)
        self.assertAlmostEqual(result["drawdown"], -.2)

    def test_short_listing(self):
        self.assertEqual(calc([100, 80])["window_samples"], 2)

    def test_short_not_assumed_ipo(self):
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_HISTORY"):
            ind.calculate(series([100, 80]), series([100, 80])[-1][0])

    def test_tie_latest_date(self):
        self.assertEqual(calc([100, 100])["highest_date"], series([100, 100])[-1][0])

    def test_invalid_prices(self):
        for bad in (None, float("nan"), float("inf"), 0, -1, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                calc([100, bad])

    def test_missing_session(self):
        rows = series([100] * 4)
        del rows[1]
        with self.assertRaisesRegex(ValueError, "missing trading date"):
            ind.calculate(rows, rows[-1][0], True)

    def test_duplicate_and_unsorted(self):
        for rows in (series([100] * 3)[::-1], [series([100])[0]] * 2):
            with self.assertRaises(ValueError):
                ind.calculate(rows, rows[-1][0], True)

    def test_stale_target(self):
        with self.assertRaisesRegex(ValueError, "STALE_DATA"):
            ind.calculate(series([100] * 3), "2026-10-29", True)

    def test_rsi_rising(self):
        self.assertEqual(ind.wilder_rsi(list(range(1, 101))), 100)

    def test_rsi_falling(self):
        self.assertEqual(ind.wilder_rsi(list(range(100, 0, -1))), 0)

    def test_rsi_flat(self):
        self.assertEqual(ind.wilder_rsi([100] * 50), 50)

    def test_rsi_14_prices_insufficient(self):
        self.assertIsNone(ind.wilder_rsi([100] * 14))

    def test_wilder_published_example_and_independent_decimal(self):
        # Classic hand-worked Wilder example: first RSI =70.4641350211.
        prices = [44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28,46.00,46.03,46.41,46.22,45.64,46.21]
        self.assertAlmostEqual(ind.wilder_rsi(prices[:15]), 70.4641350211, places=8)
        # Independent expanded weighted sum, no recursive smoothing loop.
        with localcontext() as ctx:
            ctx.prec = 50
            values = [Decimal(str(p)) for p in prices]
            changes = [b-a for a,b in zip(values, values[1:])]
            q, n = Decimal(13)/14, len(changes)-14
            gain = sum(max(x, Decimal(0)) for x in changes[:14])/14*q**n
            loss = sum(max(-x, Decimal(0)) for x in changes[:14])/14*q**n
            for j, change in enumerate(changes[14:]):
                gain += max(change, Decimal(0))/14*q**(n-1-j)
                loss += max(-change, Decimal(0))/14*q**(n-1-j)
            expected = float(100-100/(1+gain/loss))
        self.assertAlmostEqual(ind.wilder_rsi(prices), expected, places=10)

    def test_sma50(self):
        self.assertEqual(ind.sma(list(range(1, 51)), 50), 25.5)

    def test_sma200(self):
        self.assertEqual(ind.sma(list(range(1, 201)), 200), 100.5)

    def test_sma_insufficient(self):
        self.assertIsNone(ind.sma([1] * 199, 200))

    def test_sma_includes_latest(self):
        self.assertEqual(ind.sma([1000] + [1]*49 + [51], 50), 2)


class SignalTests(unittest.TestCase):
    def step(self, old, drawdown, date="2026-10-29", revision=False, pp=1):
        current = {"drawdown": drawdown, "trading_date": date}
        return {**current, **signals.transition(old, current, revision, pp)}

    def test_baseline_no_new_signals(self):
        row = self.step(None, -.33)
        self.assertEqual(row["change_event"], "FIRST_BASELINE")
        self.assertEqual(row["new_thresholds"], [])

    def test_all_three_thresholds(self):
        old = self.step(None, -.08, "2026-10-26")
        for date, price, expected in [("2026-10-27",-.12,10),("2026-10-28",-.24,20),("2026-10-29",-.33,30)]:
            old = self.step(old, price, date)
            self.assertEqual(old["change_event"], "NEW_THRESHOLD")
            self.assertEqual(old["new_thresholds"], [expected])

    def test_multiple_crossings(self):
        old = self.step(None, -.08, "2026-10-28")
        self.assertEqual(self.step(old, -.23)["crossed_thresholds_this_run"], [10,20])

    def test_recovery_and_reentry(self):
        old = self.step(None, -.33, "2026-10-27")
        recovery = self.step(old, -.18, "2026-10-28")
        self.assertEqual(recovery["change_event"], "RECOVERY")
        row = self.step(recovery, -.24)
        self.assertEqual(row["change_event"], "REENTRY")
        self.assertEqual(row["reentered_thresholds"], [20])

    def test_same_day_no_duplicate(self):
        old = self.step(None, -.12)
        self.assertEqual(self.step(old, -.12)["change_event"], "NO_CHANGE")

    def test_revision_not_market_drop(self):
        old = self.step(None, -.08, "2026-10-28")
        row = self.step(old, -.24, revision=True)
        self.assertEqual(row["change_event"], "HISTORICAL_REVISION")
        self.assertEqual(row["crossed_thresholds_this_run"], [])

    def test_deepening_percentage_points(self):
        old = self.step(None, -.12, "2026-10-28")
        self.assertEqual(self.step(old, -.125, pp=1)["change_event"], "NO_CHANGE")
        self.assertEqual(self.step(old, -.13, pp=1)["change_event"], "DEEPER_DRAWDOWN")
        self.assertEqual(self.step(old, -.125, pp=.4)["change_event"], "DEEPER_DRAWDOWN")

    def test_accumulated_deepening_anchor(self):
        old = self.step(None, -.12, "2026-10-27")
        old = self.step(old, -.126, "2026-10-28")
        self.assertEqual(self.step(old, -.132)["change_event"], "DEEPER_DRAWDOWN")

    def test_invalid_configuration(self):
        for pp in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                self.step(None, -.1, pp=pp)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence, cls.diag = monitor.read_input(monitor.DEFAULT_INPUT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def execute(self):
        with patch("sys.stdout", new=io.StringIO()):
            return monitor.run(state_path=self.path/"state.json", output_dir=self.path)

    def test_baseline_repeat_state_unchanged_and_recovery(self):
        first = self.execute()
        before = (self.path/"state.json").read_bytes()
        again = self.execute()
        self.assertEqual(first["success_count"], 9)
        self.assertTrue(all(s["change_event"] == "FIRST_BASELINE" for s in first["stocks"]))
        self.assertTrue(all(s["change_event"] == "NO_CHANGE" for s in again["stocks"]))
        self.assertFalse(again["state_updated"])
        self.assertEqual(before, (self.path/"state.json").read_bytes())
        self.assertEqual(len(state.load(self.path/"state.json")["stocks"]), 9)

    def test_corrupted_state_never_reset(self):
        p = self.path/"state.json"
        for text in ("{broken", '{"schema_version":1,"rules_version":"wrong","stocks":{}}'):
            p.write_text(text)
            with self.assertRaises(state.StateError):
                self.execute()
            self.assertEqual(p.read_text(), text)

    def test_failed_stock_preserves_state_others_continue(self):
        self.execute()
        before = state.load(self.path/"state.json")["stocks"]["AAPL"]
        broken = copy.deepcopy(self.evidence)
        broken["stocks"]["AAPL"]["rows"][-1]["adjclose"] = None
        with patch.object(monitor, "read_input", return_value=(broken, self.diag)):
            report = self.execute()
        self.assertEqual(report["success_count"], 8)
        self.assertEqual(report["stocks"][1]["change_event"], "DATA_ERROR")
        self.assertEqual(before, state.load(self.path/"state.json")["stocks"]["AAPL"])

    def test_spcx_independent_indicator_availability(self):
        report = self.execute()
        row = next(r for r in report["stocks"] if r["symbol"] == "SPCX")
        self.assertEqual(row["window_samples"], 97)
        self.assertIsNone(row["sma200"])
        self.assertTrue(all(row[k] is not None for k in ("drawdown","rsi14","sma50")))
        self.assertFalse(row["historical_anomaly"]["adjclose_conflict_established"])
        self.assertEqual(row["data_quality"], "PASS_PROVISIONAL")

    def test_close_not_used_in_indicators(self):
        stock = copy.deepcopy(self.evidence["stocks"]["NVDA"])
        first, _ = monitor.process_symbol("NVDA", stock, self.diag["NVDA"], None, 1)
        for row in stock["rows"]:
            row["close"] *= 2
        second, _ = monitor.process_symbol("NVDA", stock, self.diag["NVDA"], None, 1)
        for key in ("drawdown","highest_adjclose","rsi14","sma50","sma200"):
            self.assertEqual(first[key], second[key])

    def test_revision_overlapping_date_recomputes(self):
        stock = copy.deepcopy(self.evidence["stocks"]["NVDA"])
        first, previous = monitor.process_symbol("NVDA", stock, self.diag["NVDA"], None, 1)
        stock["rows"][-2]["adjclose"] *= 1.5
        row, updated = monitor.process_symbol("NVDA", stock, self.diag["NVDA"], previous, 1)
        self.assertEqual(row["change_event"], "HISTORICAL_REVISION")
        self.assertEqual(row["historical_revision_count"], 1)
        self.assertNotEqual(row["rsi14"], first["rsi14"])
        self.assertEqual(monitor.process_symbol("NVDA", stock, self.diag["NVDA"], updated, 1)[0]["change_event"], "NO_CHANGE")

    def test_rolling_hash_not_revision(self):
        previous = {"history_prices": {"a": 10, "b": 20}}
        self.assertEqual(state.revisions(previous, {"b":20,"c":30}), [])

    def test_revision_tolerance(self):
        self.assertEqual(state.revisions({"history_prices":{"a":100}}, {"a":100+1e-9}), [])

    def test_old_snapshot_cannot_overwrite_new_state(self):
        stock = self.evidence["stocks"]["NVDA"]
        with self.assertRaisesRegex(ValueError, "STALE_DATA"):
            monitor.process_symbol("NVDA", stock, self.diag["NVDA"], {"trading_date":"2026-10-30"}, 1)

    def test_input_hash_tampering_rejected(self):
        changed = copy.deepcopy(self.evidence)
        changed["stocks"]["NVDA"]["rows"][0]["adjclose"] += 1
        path = self.path/"prices.json"
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "INPUT_INTEGRITY_ERROR"):
            monitor.read_input(path)

    def test_all_nine_independent_decimal_reference(self):
        for symbol in state.SYMBOLS:
            with self.subTest(symbol=symbol), localcontext() as ctx:
                ctx.prec = 50
                stock = self.evidence["stocks"][symbol]
                row, _ = monitor.process_symbol(symbol, stock, self.diag[symbol], None, 1)
                values = [Decimal(str(r["adjclose"])) for r in stock["rows"]]
                dd = values[-1]/max(values[-252:])-1
                self.assertAlmostEqual(row["drawdown"], float(dd), places=12)
                for n in (50, 200):
                    if len(values) >= n:
                        self.assertAlmostEqual(row[f"sma{n}"], float(sum(values[-n:])/n), places=10)
                delta = [b-a for a,b in zip(values, values[1:])]
                q, n = Decimal(13)/14, len(delta)-14
                g = sum(max(d, Decimal(0)) for d in delta[:14])/14*q**n
                loss = sum(max(-d, Decimal(0)) for d in delta[:14])/14*q**n
                g += sum(max(d, Decimal(0))/14*q**(n-j-1) for j,d in enumerate(delta[14:]))
                loss += sum(max(-d, Decimal(0))/14*q**(n-j-1) for j,d in enumerate(delta[14:]))
                self.assertAlmostEqual(row["rsi14"], float(100-100/(1+g/loss)), places=9)

    def test_logically_corrupt_state_fails_closed(self):
        self.execute()
        p = self.path/"state.json"
        data = json.loads(p.read_text())
        data["stocks"]["NVDA"]["sma50"] += 1
        p.write_text(json.dumps(data))
        with self.assertRaises(state.StateError):
            state.load(p)

    def test_missing_stock_in_partial_fetch_keeps_others(self):
        broken = copy.deepcopy(self.evidence)
        del broken["stocks"]["AAPL"]
        with patch.object(monitor, "read_input", return_value=(broken, self.diag)):
            report = self.execute()
        self.assertEqual(report["success_count"], 8)
        self.assertEqual(report["failure_count"], 1)


if __name__ == "__main__":
    unittest.main()
