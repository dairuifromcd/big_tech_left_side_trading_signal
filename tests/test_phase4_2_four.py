"""Offline guards for the four-day replacement plan; never requests Yahoo."""
import copy
import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from diagnostics import phase4_2_four as four
from src import phase4_2 as common, state


class FourDayGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_file = self.root / "config.json"
        self.config_file.write_text("{}")
        self.checkpoint_file = self.root / "state.json"
        self.checkpoint_file.write_text("trusted seeded checkpoint")
        self.config = {"state_path": str(self.checkpoint_file), "initial_state_sha256": common.digest(self.checkpoint_file),
                       "baseline": {"trading_date": "2026-11-02"}}
        self.ledger = {"trial_id": four.IDENTITY, "status": "ARMED", "config_sha256": common.digest(self.config_file),
                       "runs": [{"plan": copy.deepcopy(p), "claimed": False, "result": "PENDING"} for p in four.PLAN]}
        self.checkpoint = {"trial_id": four.IDENTITY, "schema_version": 2,
                           "stocks": {s: {"trading_date": "2026-11-02"} for s in state.SYMBOLS}}
        self.now = dt.datetime.fromisoformat(four.PLAN[0]["scheduled_brisbane"])
        for name, value in (("BASE", self.root), ("CONFIG", self.config_file)):
            context = patch.object(four, name, value)
            context.start(); self.addCleanup(context.stop)

    def check(self, number=1, now=None):
        four.guard(self.config, self.ledger, self.checkpoint, number, now or self.now)

    def reject(self, text, number=1, now=None):
        with self.assertRaisesRegex(common.GuardError, text):
            self.check(number, now)

    def test_first_run_continues_verified_manual_baseline(self):
        self.check()

    def test_exact_four_dates_and_completed_targets(self):
        self.assertEqual(len(four.PLAN), 4)
        for number, row in enumerate(four.PLAN, 1):
            self.assertEqual(row["scheduled_brisbane"], f"2026-11-{number+3:02d}T10:00:00+10:00")
            self.assertEqual(four.calendar.latest_completed_session(dt.datetime.fromisoformat(row["scheduled_brisbane"])).isoformat(), row["target_date"])

    def test_early_launch_has_no_capture_permission(self):
        self.reject("OUTSIDE_WINDOW", now=self.now-dt.timedelta(seconds=1))

    def test_fifteen_minute_late_launch_refused(self):
        self.reject("OUTSIDE_WINDOW", now=self.now+dt.timedelta(minutes=15))

    def test_expired_plan_refused(self):
        self.reject("OUTSIDE_WINDOW", now=dt.datetime(2026, 11, 8, 10, tzinfo=common.ZONE))

    def test_fifth_collection_attempt_refused(self):
        self.reject("ATTEMPT_LIMIT", number=5)

    def test_four_failures_exhaust_limit(self):
        for row in self.ledger["runs"]:
            row.update(claimed=True, result="DATA_ERROR")
        self.reject("ATTEMPT_LIMIT")

    def test_duplicate_claim_refused(self):
        self.ledger["runs"][0].update(claimed=True, result="SUCCESS")
        self.reject("DUPLICATE_CLAIM")

    def test_uncertain_crash_refused(self):
        self.ledger["runs"][0].update(claimed=True, result="CLAIMED")
        self.reject("UNCERTAIN_CAPTURE", 2, dt.datetime.fromisoformat(four.PLAN[1]["scheduled_brisbane"]))

    def test_terminal_states_refused(self):
        for value in common.TERMINAL:
            with self.subTest(status=value):
                self.ledger["status"] = value
                self.reject("TRIAL_TERMINAL")

    def test_pending_or_failed_previous_day_refused(self):
        for value in ("PENDING", "DATA_ERROR", "PARTIAL_SUCCESS", "RATE_LIMITED"):
            with self.subTest(result=value):
                self.ledger["runs"][0].update(claimed=value != "PENDING", result=value)
                self.reject("CATCHUP_REQUIRED", 2, dt.datetime.fromisoformat(four.PLAN[1]["scheduled_brisbane"]))

    def test_changed_checkpoint_refused(self):
        self.checkpoint_file.write_text("unexpected different checkpoint")
        self.reject("STATE_CONTINUITY")

    def test_wrong_trial_state_refused(self):
        self.checkpoint["trial_id"] = "different-worktree"
        self.reject("STATE_IDENTITY")

    def test_single_stock_gap_refused(self):
        self.checkpoint["stocks"]["NVDA"]["trading_date"] = "2026-10-29"
        self.reject("CATCHUP_REQUIRED")

    def test_calendar_target_mismatch_refused(self):
        with patch.object(four.calendar, "latest_completed_session", return_value=dt.date(2026, 11, 2)):
            self.reject("CALENDAR_TARGET_MISMATCH")

    def test_config_change_refused(self):
        self.config_file.write_text('{"changed":true}')
        self.reject("LEDGER_INTEGRITY")

    def test_second_run_requires_exact_last_success_hash_and_date(self):
        self.ledger["runs"][0].update(claimed=True, result="SUCCESS", state_hash_after=common.digest(self.checkpoint_file))
        for stock in self.checkpoint["stocks"].values():
            stock["trading_date"] = "2026-11-03"
        self.check(2, dt.datetime.fromisoformat(four.PLAN[1]["scheduled_brisbane"]))

    def test_external_persistent_block_refused(self):
        (self.root / "acceptance").mkdir()
        (self.root / "acceptance/BLOCKED.json").write_text('{"reason":"uncertain request"}')
        self.reject("TRIAL_TERMINAL_OR_BLOCKED")


class FourDayScheduleTests(unittest.TestCase):
    def test_calendar_jobs_do_not_run_on_install_or_restart_continuously(self):
        row = four.launch_job(four.PREFIX+"run1", ["supervise", "1"], four.PLAN[0]["scheduled_brisbane"])
        self.assertEqual(row["StartCalendarInterval"], {"Month": 11, "Day": 4, "Hour": 10, "Minute": 0})
        self.assertFalse(row["RunAtLoad"])
        self.assertFalse(row["KeepAlive"])
        self.assertTrue(row["LaunchOnlyOnce"])
        self.assertIn("TMPDIR", row["EnvironmentVariables"])

    def test_deadline_invokes_only_summary_cleanup(self):
        with patch.object(four, "detached_cleanup") as cleanup, patch.object(four.subprocess, "run") as run:
            four.supervise("deadline")
            run.assert_not_called()
            cleanup.assert_called_once_with("all", "DEADLINE_SUMMARY_ONLY")

    def test_summary_future_rows_remain_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/"acceptance").mkdir()
            config = {"baseline": {"trading_date": "2026-11-02", "source_state": "verified-manual.json"}, "state_path": "isolated.json"}
            ledger = {"status": "ARMED", "runs": [{"plan": copy.deepcopy(p), "claimed": False, "result": "PENDING"} for p in four.PLAN]}
            with patch.object(four, "BASE", root), patch.object(common, "protected_differences", return_value=[]):
                result = four.summarize(config, ledger)
            self.assertEqual(result["result"], "PENDING")
            self.assertFalse(result["final"])
            self.assertEqual(result["claimed_attempts"], 0)
            self.assertTrue(all(r["result"] == "PENDING" for r in result["runs"]))


if __name__ == "__main__":
    unittest.main()
