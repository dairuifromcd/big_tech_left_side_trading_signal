"""Strictly offline Phase 4.1 regression tests; formal state is read-only."""

import copy
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from diagnostics import revision_scenarios
import market_calendar as calendar
from src import indicators, monitor, state


ROOT = Path(__file__).resolve().parents[1]
FORMAL = ROOT / "state/monitor_state.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def process(pairs, previous=None, closes=None, symbol="NVDA"):
    stock, diagnostic = revision_scenarios._snapshot(pairs)
    if closes:
        for row in stock["rows"]:
            row["close"] = closes.get(row["trading_date"], row["close"])
    if symbol != "NVDA":
        names = {"AAPL": "Apple Inc"}
        stock["symbol"] = diagnostic["symbol"] = symbol
        diagnostic["identity"].update({"symbol": symbol, "longName": names[symbol]})
    return monitor.process_symbol(symbol, stock, diagnostic, previous, 1.0)


def levels(observation, key):
    values = observation.get("threshold_state", {}).get(key, [])
    return {int(value) for value in values}


def market_events(observation, threshold=None):
    events = observation.get("market_events", [])
    return [event for event in events if threshold is None or event.get("threshold") == threshold]


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.formal_hash = digest(FORMAL)
        for target in ("socket.getaddrinfo", "socket.create_connection",
                       "http.client.HTTPConnection.connect", "http.client.HTTPSConnection.connect"):
            blocker = patch(target, side_effect=AssertionError("Phase 4.1 must stay offline"))
            blocker.start()
            self.addCleanup(blocker.stop)

    def tearDown(self):
        self.assertEqual(self.formal_hash, digest(FORMAL), "Formal state must remain byte-for-byte unchanged")


class P0RevisionAndMarketEventTests(OfflineCase):
    def test_scenario_b_preserves_twenty_percent_market_candidate(self):
        """An old low revision must not erase or pre-consume the new -20% event."""
        pairs, next_day = revision_scenarios._base_pairs()
        _, previous = revision_scenarios._process(pairs)
        revised = list(pairs)
        revised[10] = (revised[10][0], 90.0001)
        revised.append((next_day, 79.0))
        observation, updated = revision_scenarios._process(revised, previous)
        self.assertEqual(observation["historical_revision_count"], 1)
        market = observation.get("market_observation", {})
        candidates = set(market.get("candidate_thresholds", []))
        candidates.update(observation.get("crossed_thresholds_this_run", []))
        candidates.update(observation.get("new_thresholds", []))
        self.assertIn(20, candidates, (
            "P0: real WATCH_20 event vanished while a historical revision was present; "
            f"change_event={observation['change_event']}, "
            f"crossed={observation['crossed_thresholds_this_run']}, "
            f"new={observation['new_thresholds']}, "
            f"triggered={updated['triggered_thresholds']}"
        ))
        confirmed = levels(updated, "confirmed")
        pending = {event["threshold"] for event in market_events(updated)
                   if event["status"] == "PENDING_REVIEW" and event.get("threshold") is not None}
        self.assertTrue(20 in confirmed or 20 in pending,
                        "WATCH_20 must be durably confirmed or pending, never lost.")
        if 20 not in confirmed:
            self.assertNotIn(20, updated["triggered_thresholds"],
                             "An unconfirmed event must not consume first-confirmation eligibility.")

    def test_b_stable_close_evidence_confirms_real_new_twenty_percent_event(self):
        pairs, next_day = revision_scenarios._base_pairs()
        _, previous = process(pairs)
        revised = list(pairs)
        revised[10] = (revised[10][0], 90.0001)
        revised.append((next_day, 79.0))
        observation, updated = process(revised, previous, closes=dict(pairs))
        self.assertTrue(observation["revision_observation"]["detected"])
        self.assertEqual(observation["revision_observation"]["count"], 1)
        self.assertEqual(observation["watch_tier"], "WATCH_20")
        self.assertIn(20, observation["market_observation"]["candidate_thresholds"])
        self.assertTrue(observation["market_observation"]["can_confirm"])
        events = market_events(observation, 20)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "CONFIRMED")
        self.assertIn(20, levels(updated, "confirmed"))


class ObservationScenarios(OfflineCase):
    def setUp(self):
        super().setUp()
        self.pairs, self.next_day = revision_scenarios._base_pairs()
        self.before, self.previous = process(self.pairs)

    def revised_low(self):
        revised = list(self.pairs)
        revised[10] = (revised[10][0], 90.0001)
        return revised

    def next_session(self, day):
        return calendar.sessions_between(dt.date.fromisoformat(day) + dt.timedelta(days=1), dt.date(2026, 12, 31))[0].isoformat()

    def test_a_micro_revision_alone_keeps_revision_fact_without_market_event(self):
        observation, updated = process(self.revised_low(), self.previous, closes=dict(self.pairs))
        self.assertTrue(observation["revision_observation"]["detected"])
        self.assertEqual(observation["historical_revision_count"], 1)
        self.assertEqual(observation["watch_tier"], "WATCH_10")
        self.assertEqual(market_events(observation), [])
        self.assertEqual(levels(updated, "confirmed"), levels(self.previous, "confirmed"))

    def test_c_historical_high_revision_alone_does_not_confirm_market_crossing(self):
        revised = list(self.pairs)
        revised[1] = (revised[1][0], 110.0)
        observation, updated = process(revised, self.previous, closes=dict(self.pairs))
        self.assertTrue(observation["revision_observation"]["detected"])
        self.assertEqual(observation["watch_tier"], "WATCH_20")
        self.assertAlmostEqual(observation["drawdown"], 85 / 110 - 1)
        self.assertFalse(any(event["status"] == "CONFIRMED" for event in market_events(observation, 20)))
        self.assertNotIn(20, levels(updated, "confirmed"))

    def test_d_mixed_high_revision_and_new_price_remains_pending(self):
        revised = list(self.pairs)
        revised[1] = (revised[1][0], 110.0)
        revised.append((self.next_day, 81.0))
        observation, updated = process(revised, self.previous, closes=dict(self.pairs))
        self.assertTrue(observation["revision_observation"]["detected"])
        self.assertEqual(observation["watch_tier"], "WATCH_20")
        self.assertFalse(observation["market_observation"]["can_confirm"])
        self.assertIn(20, observation["market_observation"]["candidate_thresholds"])
        self.assertTrue(market_events(observation, 20))
        self.assertTrue(all(event["status"] == "PENDING_REVIEW" for event in market_events(observation, 20)))
        self.assertNotIn(20, levels(updated, "confirmed"))
        self.assertNotIn(20, updated["triggered_thresholds"])

    def test_e_repeating_same_snapshot_has_no_duplicate_market_event(self):
        revised = self.revised_low() + [(self.next_day, 79.0)]
        first, accepted = process(revised, self.previous)
        again, repeated = process(revised, accepted)
        self.assertEqual(market_events(again), [])
        self.assertEqual(again["historical_revision_count"], 0)
        self.assertEqual(again["change_event"], "NO_CHANGE")
        self.assertEqual(repeated["history_fingerprint"], accepted["history_fingerprint"])
        self.assertEqual(levels(repeated, "confirmed"), levels(accepted, "confirmed"))
        self.assertEqual(repeated["threshold_state"].get("pending"), accepted["threshold_state"].get("pending"))

    def test_f_same_day_new_micro_capture_never_becomes_new_market_day(self):
        revised = self.revised_low()
        first, previous = process(revised, self.previous, closes=dict(self.pairs))
        revised[11] = (revised[11][0], 89.9999)
        again, updated = process(revised, previous, closes=dict(self.pairs))
        self.assertTrue(again["revision_observation"]["detected"])
        self.assertEqual(again["trading_date"], self.before["trading_date"])
        self.assertEqual(market_events(again), [])
        self.assertEqual(levels(updated, "confirmed"), levels(self.previous, "confirmed"))

    def test_g_new_day_can_cross_ten_and_twenty_together(self):
        pairs = list(self.pairs)
        pairs[-1] = (pairs[-1][0], 95.0)
        _, previous = process(pairs)
        observation, updated = process(pairs + [(self.next_day, 79.0)], previous)
        confirmed = {event["threshold"] for event in market_events(observation) if event["status"] == "CONFIRMED"}
        self.assertEqual(confirmed, {10, 20})
        self.assertEqual(levels(updated, "confirmed"), {10, 20})
        self.assertFalse(observation["revision_observation"]["detected"])

    def test_h_recovery_then_reentry_preserves_first_confirmation_history(self):
        # Keep the100 high inside all four windows: the original diagnostic
        # intentionally placed it near the left edge and it would expire here.
        base = list(self.pairs)
        base[1] = (base[1][0], 90.0)
        base[50] = (base[50][0], 100.0)
        _, baseline = process(base)
        pairs = base + [(self.next_day, 79.0)]
        _, previous = process(pairs, baseline)
        recovery_day = self.next_session(self.next_day)
        recovered_pairs = pairs + [(recovery_day, 95.0)]
        recovered, previous = process(recovered_pairs, previous)
        self.assertEqual(recovered["watch_tier"], "NONE")
        self.assertIn(20, levels(previous, "confirmed"))
        reentry_day = self.next_session(recovery_day)
        observation, updated = process(recovered_pairs + [(reentry_day, 79.0)], previous)
        events = market_events(observation, 20)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_subtype"], "REENTRY")
        self.assertEqual(events[0]["status"], "CONFIRMED")
        self.assertIn(20, levels(updated, "confirmed"))

    def test_i_natural_high_expiration_is_not_historical_revision(self):
        pairs = [(date, 120.0 if index == 0 else 100.0) for index, (date, _) in enumerate(self.pairs)]
        before, previous = process(pairs)
        observation, _ = process(pairs + [(self.next_day, 101.0)], previous)
        self.assertEqual(before["highest_adjclose"], 120.0)
        self.assertEqual(observation["highest_adjclose"], 101.0)
        self.assertEqual(observation["drawdown"], 0)
        self.assertFalse(observation["revision_observation"]["detected"])
        self.assertFalse(any(event["event_type"] == "THRESHOLD_CROSSING" for event in market_events(observation)))

    def test_j_float32_high_revision_near_boundary_is_not_automatically_harmless(self):
        pairs = list(self.pairs)
        pairs[-1] = (pairs[-1][0], 90.000001)
        before, previous = process(pairs)
        revised = list(pairs)
        revised[1] = (revised[1][0], 100.00000762939453)
        observation, updated = process(revised, previous, closes=dict(pairs))
        self.assertEqual(before["watch_tier"], "NONE")
        self.assertEqual(observation["watch_tier"], "WATCH_10")
        self.assertTrue(observation["revision_observation"]["detected"])
        self.assertNotIn(10, levels(updated, "confirmed"))
        self.assertFalse(any(event["status"] == "CONFIRMED" for event in market_events(observation, 10)))

    def test_k_material_adjustment_unit_change_does_not_confirm_market_event(self):
        revised = [(date, price / 2) for date, price in self.pairs] + [(self.next_day, 39.5)]
        close_map = {**dict(self.pairs), self.next_day: 79.0}
        observation, updated = process(revised, self.previous, closes=close_map)
        self.assertTrue(observation["revision_observation"]["detected"])
        self.assertFalse(observation["market_observation"]["can_confirm"])
        self.assertTrue(market_events(observation))
        self.assertTrue(all(event["status"] == "PENDING_REVIEW" for event in market_events(observation)))
        self.assertNotIn(20, levels(updated, "confirmed"))

    def test_l_normal_close_move_with_incomparable_adjclose_is_pending(self):
        revised = self.pairs + [(self.next_day, 39.5)]
        observation, updated = process(revised, self.previous, closes={self.next_day: 79.0})
        self.assertFalse(observation["market_observation"]["can_confirm"])
        self.assertTrue(market_events(observation))
        self.assertTrue(all(event["status"] == "PENDING_REVIEW" for event in market_events(observation)))
        self.assertNotIn(20, levels(updated, "confirmed"))
        self.assertNotIn(30, levels(updated, "confirmed"))

    def test_m_short_spcx_stays_provisional_with_unavailable_sma200(self):
        evidence, diagnostics = monitor.read_input(monitor.DEFAULT_INPUT)
        observation, updated = monitor.process_symbol("SPCX", evidence["stocks"]["SPCX"], diagnostics["SPCX"], None, 1.0)
        self.assertEqual(observation["data_quality"], "PASS_PROVISIONAL")
        self.assertLess(observation["window_samples"], 252)
        self.assertIsNone(observation["sma200"])
        self.assertEqual(observation["indicator_status"]["sma200"], "INSUFFICIENT_HISTORY")
        self.assertFalse(any(event["status"] == "CONFIRMED" for event in market_events(observation)))

    def test_n_one_pending_symbol_does_not_block_other_valid_symbol(self):
        revised = self.revised_low() + [(self.next_day, 79.0)]
        pending, _ = process(revised, self.previous)
        self.assertTrue(any(event["status"] == "PENDING_REVIEW" for event in market_events(pending)))
        _, apple_previous = process(self.pairs, symbol="AAPL")
        apple, updated = process(self.pairs + [(self.next_day, 79.0)], apple_previous, symbol="AAPL")
        self.assertEqual(apple["symbol"], "AAPL")
        self.assertTrue(any(event["status"] == "CONFIRMED" and event["threshold"] == 20 for event in market_events(apple)))
        self.assertIn(20, levels(updated, "confirmed"))


class PersistenceAndMigrationScenarios(OfflineCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.json"
        shutil.copyfile(FORMAL, self.path)

    def migrated(self):
        state.migrate_path(self.path)
        return state.load(self.path)

    def pending_event(self, document, event_type="THRESHOLD_CROSSING", evidence=None):
        event_id, _ = state.register_event(document, {
            "symbol": "NVDA", "trading_date": "2026-10-29", "event_type": event_type,
            "threshold": 20 if event_type == "THRESHOLD_CROSSING" else None,
            "status": "PENDING_REVIEW", "evidence": evidence or {"fixture": "pending-market-candidate"},
        })
        stock = document["stocks"]["NVDA"]
        if event_id not in stock["threshold_state"]["pending_event_ids"]:
            stock["threshold_state"]["pending_event_ids"].append(event_id)
        return event_id

    def test_n_e_pending_and_confirmed_symbols_commit_together_and_repeat_is_byte_idempotent(self):
        pairs, next_day = revision_scenarios._base_pairs()
        _, nvda_previous = process(pairs)
        _, apple_previous = process(pairs, symbol="AAPL")
        candidate, _ = state.migrate({"schema_version": 1, "rules_version": indicators.RULES_VERSION, "stocks": {}})
        candidate["stocks"] = {"NVDA": nvda_previous, "AAPL": apple_previous}
        self.path.unlink()
        state.initialize(self.path, candidate)  # Explicit initialization of this fresh fixture.

        evidence, diagnostics = monitor.read_input(monitor.DEFAULT_INPUT)
        revised = list(pairs)
        revised[10] = (revised[10][0], 90.0001)
        nvda, nvda_diagnostic = revision_scenarios._snapshot(revised + [(next_day, 79.0)])
        apple, apple_diagnostic = revision_scenarios._snapshot(pairs + [(next_day, 79.0)])
        apple["symbol"] = apple_diagnostic["symbol"] = "AAPL"
        apple_diagnostic["identity"].update({"symbol": "AAPL", "longName": "Apple Inc"})
        evidence["stocks"].update({"NVDA": nvda, "AAPL": apple})
        diagnostics.update({"NVDA": nvda_diagnostic, "AAPL": apple_diagnostic})
        with patch.object(monitor, "read_input", return_value=(evidence, diagnostics)), patch("sys.stdout", new=io.StringIO()):
            report = monitor.run(state_path=self.path, output_dir=Path(self.tmp.name) / "reports")
        self.assertEqual(report["success_count"], 9)
        self.assertEqual(report["failure_count"], 0)
        stored = state.load(self.path)
        confirmed = [event for event in stored["event_records"].values()
                     if event["symbol"] == "AAPL" and event["event_type"] == "THRESHOLD_CROSSING"]
        self.assertEqual(len(confirmed), 1)
        self.assertEqual((confirmed[0]["threshold"], confirmed[0]["status"]), (20, "CONFIRMED"))
        pending = [event for event in stored["event_records"].values()
                   if event["symbol"] == "NVDA" and event["event_type"] == "THRESHOLD_CROSSING"]
        self.assertEqual(len(pending), 1)
        self.assertEqual((pending[0]["threshold"], pending[0]["status"]), (20, "PENDING_REVIEW"))
        self.assertIn(pending[0]["event_id"], stored["stocks"]["NVDA"]["threshold_state"]["pending_event_ids"])
        self.assertNotIn(20, stored["stocks"]["NVDA"]["confirmed_thresholds"])
        self.assertNotIn(20, stored["stocks"]["NVDA"]["triggered_thresholds"])
        accepted_hash = digest(self.path)
        with patch.object(monitor, "read_input", return_value=(evidence, diagnostics)), patch("sys.stdout", new=io.StringIO()):
            again = monitor.run(state_path=self.path, output_dir=Path(self.tmp.name) / "reports")
        self.assertFalse(again["state_updated"])
        self.assertEqual(again["new_observation_events"], [])
        self.assertEqual(accepted_hash, digest(self.path))
        self.assertEqual(state.load(self.path)["event_records"][pending[0]["event_id"]]["status"], "PENDING_REVIEW")

    def test_o_failed_atomic_commit_preserves_old_state_and_explicit_backup_recovery(self):
        old = state.load(self.path)
        old_hash = digest(self.path)
        replacement, _ = state.migrate(old)
        original_replace = os.replace
        def fail_commit(source, destination):
            if Path(destination) == self.path:
                raise OSError("injected before state replacement")
            return original_replace(source, destination)
        with state.lock(self.path), patch.object(state.os, "replace", side_effect=fail_commit):
            with self.assertRaises(OSError):
                state.save(self.path, replacement)
        self.assertEqual(old_hash, digest(self.path))
        self.assertEqual(state.load(self.path), old)
        backups = list(self.path.with_name("state.json.backups").glob("*.json"))
        self.assertTrue(backups)
        self.path.write_text("intentionally damaged isolated state")
        restored = state.recover(self.path, backups[-1])
        self.assertTrue(restored["recovered"])
        self.assertEqual(state.load(self.path), old)

    def test_p_migration_is_pure_preserves_prices_and_is_byte_idempotent(self):
        original = state.load(self.path)
        untouched = copy.deepcopy(original)
        migrated, report = state.migrate(original)
        self.assertEqual(original, untouched)
        self.assertEqual(migrated["schema_version"], 2)
        self.assertTrue(report["changed"])
        for symbol, old in original["stocks"].items():
            new = migrated["stocks"][symbol]
            for key in ("history_prices", "history_fingerprint", "trading_date", "adjclose", "drawdown", "rsi14", "sma50", "sma200"):
                self.assertEqual(old[key], new[key])
        state.migrate_path(self.path)
        accepted_hash = digest(self.path)
        again = state.migrate_path(self.path)
        self.assertFalse(again["changed"])
        self.assertEqual(accepted_hash, digest(self.path))
        with self.assertRaises(state.StateError):
            state.migrate_path(FORMAL)

    def test_p_malformed_migration_source_is_preserved(self):
        original = json.loads(self.path.read_text())
        first = next(iter(original["stocks"]["NVDA"]["history_prices"]))
        original["stocks"]["NVDA"]["history_prices"][first] += 1.0
        self.path.write_text(json.dumps(original))
        damaged_hash = digest(self.path)
        with self.assertRaises(state.StateError):
            state.migrate_path(self.path)
        self.assertEqual(damaged_hash, digest(self.path))

    def test_q_legacy_consumed_threshold_without_verified_event_is_ambiguous(self):
        original = state.load(self.path)
        stock = original["stocks"]["NVDA"]
        stock["triggered_thresholds"] = [10, 20]
        semantic = {"symbol": "NVDA", "trading_date": stock["trading_date"],
                    "change_event": "HISTORICAL_REVISION", "crossed_thresholds_this_run": [],
                    "rules_version": indicators.RULES_VERSION, "revision_fingerprint": stock["history_fingerprint"]}
        original["event_records"] = {state.fingerprint(semantic): {**semantic, "data_quality": "PASS"}}
        migrated, report = state.migrate(original)
        current = migrated["stocks"]["NVDA"]
        self.assertNotIn(20, current["confirmed_thresholds"])
        self.assertNotIn(20, current["triggered_thresholds"])
        ambiguities = [item for item in report["ambiguous_thresholds"] if item["symbol"] == "NVDA" and item["threshold"] == 20]
        self.assertEqual(len(ambiguities), 1)
        self.assertEqual(migrated["event_records"][ambiguities[0]["event_id"]]["status"], "PENDING_REVIEW")

    def test_r_pending_event_promotes_in_place_only_after_explicit_review(self):
        document = self.migrated()
        event_id = self.pending_event(document)
        count = len(document["event_records"])
        stable, new = state.register_event(document, {
            "symbol": "NVDA", "trading_date": "2026-10-29", "event_type": "THRESHOLD_CROSSING",
            "threshold": 20, "status": "CONFIRMED", "evidence": {"fixture": "later-supporting-evidence"},
        })
        self.assertEqual(stable, event_id)
        self.assertFalse(new)
        self.assertEqual(document["event_records"][event_id]["status"], "PENDING_REVIEW")
        self.assertEqual(len(document["event_records"]), count)
        with state.lock(self.path):
            state.save(self.path, document)
        keep = state.review_event(self.path, event_id, "KEEP", "Need independent attribution review")
        self.assertEqual(keep["status"], "PENDING_REVIEW")
        confirmed = state.review_event(self.path, event_id, "CONFIRM", "Independent review confirms comparable market event")
        self.assertEqual(confirmed["event_id"], event_id)
        self.assertEqual(confirmed["status"], "CONFIRMED")
        self.assertEqual(confirmed["delivery"], "NONE")
        loaded = state.load(self.path)
        self.assertEqual(len(loaded["event_records"]), count)
        self.assertIn(20, loaded["stocks"]["NVDA"]["confirmed_thresholds"])
        self.assertNotIn(event_id, loaded["stocks"]["NVDA"]["threshold_state"]["pending_event_ids"])
        self.assertEqual(loaded["event_records"][event_id]["audit_trail"][-1]["from_status"], "PENDING_REVIEW")
        final_hash = digest(self.path)
        repeated = state.review_event(self.path, event_id, "CONFIRM", "Same confirmation repeated")
        self.assertFalse(repeated["changed"])
        self.assertEqual(final_hash, digest(self.path))

    def test_r_event_ids_separate_revision_and_market_and_ignore_evidence_time(self):
        document = self.migrated()
        event_id = self.pending_event(document)
        again, new = state.register_event(document, {
            "symbol": "NVDA", "trading_date": "2026-10-29", "event_type": "THRESHOLD_CROSSING",
            "threshold": 20, "status": "PENDING_REVIEW", "evidence": {"new_capture_time": "2099-01-01T00:00:00Z"},
        })
        revision_id, _ = state.register_event(document, {
            "symbol": "NVDA", "trading_date": "2026-10-29", "event_type": "REVISION_OBSERVATION",
            "status": "PENDING_REVIEW", "evidence": {"same_capture": True},
        })
        self.assertEqual(event_id, again)
        self.assertFalse(new)
        self.assertNotEqual(event_id, revision_id)
        self.assertEqual(len(document["event_records"][event_id]["evidence_versions"]), 2)

    def test_s_rejected_revision_restores_previous_valid_stock_and_blocks_bad_snapshot(self):
        document = self.migrated()
        previous = copy.deepcopy(document["stocks"]["NVDA"])
        revised = copy.deepcopy(previous)
        oldest = min(revised["history_prices"])
        revised["history_prices"][oldest] += .0001
        revised["history_fingerprint"] = state.fingerprint(revised["history_prices"])
        recalculated = indicators.calculate(sorted(revised["history_prices"].items()), revised["trading_date"])
        revised.update(recalculated)
        document["stocks"]["NVDA"] = revised
        event_id = self.pending_event(document, "REVISION_OBSERVATION", {
            "previous_valid_stock": previous, "snapshot_fingerprint": revised["history_fingerprint"],
        })
        related_id, _ = state.register_event(document, {
            "symbol": "NVDA", "trading_date": revised["trading_date"],
            "event_type": "THRESHOLD_CROSSING", "threshold": 20,
            "status": "CONFIRMED", "evidence": {"snapshot_fingerprint": revised["history_fingerprint"]},
        })
        revised["confirmed_thresholds"] = sorted(set(revised["confirmed_thresholds"]) | {20})
        revised["triggered_thresholds"] = list(revised["confirmed_thresholds"])
        revised["threshold_state"]["confirmed"] = list(revised["confirmed_thresholds"])
        with state.lock(self.path):
            state.save(self.path, document)
        result = state.review_event(self.path, event_id, "REJECT", "Revised capture independently rejected as bad data")
        self.assertTrue(result["price_checkpoint_restored"])
        restored = state.load(self.path)
        current = restored["stocks"]["NVDA"]
        self.assertEqual(current["history_prices"], previous["history_prices"])
        self.assertEqual(current["history_fingerprint"], previous["history_fingerprint"])
        self.assertIn(revised["history_fingerprint"], current["rejected_snapshot_fingerprints"])
        self.assertEqual(restored["event_records"][event_id]["status"], "REJECTED")
        self.assertTrue(restored["event_records"][event_id]["audit_trail"])
        self.assertIn(related_id, result["related_rejected_event_ids"])
        self.assertEqual(restored["event_records"][related_id]["status"], "REJECTED")
        self.assertEqual(current["confirmed_thresholds"], previous["confirmed_thresholds"])
        evidence, diagnostics = monitor.read_input(monitor.DEFAULT_INPUT)
        rejected_capture = copy.deepcopy(evidence["stocks"]["NVDA"])
        for row in rejected_capture["rows"]:
            if row["trading_date"] == oldest:
                row["adjclose"] += .0001
        with self.assertRaisesRegex(ValueError, "REJECTED_REVISION_SNAPSHOT"):
            monitor.process_symbol("NVDA", rejected_capture, diagnostics["NVDA"], current, 1.0)

    def test_t_process_lock_and_event_ledger_remain_consistent(self):
        document = self.migrated()
        before = digest(self.path)
        code = """from pathlib import Path
import sys
from src import state
path=Path(sys.argv[1])
try:
 with state.lock(path):
  doc=state.load(path)
  event_id,_=state.register_event(doc,{'symbol':'NVDA','trading_date':'2026-10-29','event_type':'THRESHOLD_CROSSING','threshold':20,'status':'PENDING_REVIEW','evidence':{'fixed':'child-process'}})
  ids=doc['stocks']['NVDA']['threshold_state']['pending_event_ids']
  if event_id not in ids:ids.append(event_id)
  state.save(path,doc)
  print(event_id)
except state.StateError:
 print('BLOCKED')
 sys.exit(73)
"""
        with state.lock(self.path):
            blocked = subprocess.run([sys.executable, "-c", code, str(self.path)], capture_output=True, text=True, timeout=5)
        self.assertEqual(blocked.returncode, 73)
        self.assertIn("BLOCKED", blocked.stdout)
        self.assertEqual(before, digest(self.path))
        first = subprocess.run([sys.executable, "-c", code, str(self.path)], capture_output=True, text=True, timeout=5)
        second = subprocess.run([sys.executable, "-c", code, str(self.path)], capture_output=True, text=True, timeout=5)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout.strip(), second.stdout.strip())
        accepted = state.load(self.path)
        self.assertEqual(len(accepted["event_records"]), len(document["event_records"]) + 1)
        stored = accepted["event_records"][first.stdout.strip()]
        self.assertEqual(len(stored["audit_trail"]), 1)
        self.assertEqual(len(stored["evidence_versions"]), 1)


if __name__ == "__main__":
    unittest.main()
