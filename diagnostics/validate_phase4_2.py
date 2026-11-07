"""Offline-only regression and readiness evidence; never invokes the live runner."""
import datetime as dt
import json
from pathlib import Path
import sys
import unittest

from src import phase4_2 as trial, state


def main():
    attempts = []

    def offline(event, args):
        if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo", "http.client.connect", "urllib.Request"):
            attempts.append(event)
            raise RuntimeError("Phase 4.2 offline preflight forbids network: " + event)

    sys.addaudithook(offline)
    directory = trial.TRIAL / "preflight"
    outcomes = []

    class Recorder(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test); outcomes.append({"id": test.id(), "status": "PASS"})

        def addFailure(self, test, err):
            super().addFailure(test, err); outcomes.append({"id": test.id(), "status": "FAIL"})

        def addError(self, test, err):
            super().addError(test, err); outcomes.append({"id": test.id(), "status": "ERROR"})

    with (directory / "regression_final.log").open("w") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=Recorder).run(unittest.defaultTestLoader.discover(str(trial.ROOT)))
    original = trial.read_json(directory / "regression_153.json")
    passed = {r["id"] for r in outcomes if r["status"] == "PASS"}
    old_retained = {r["id"] for r in original["outcomes"]}.issubset(passed)
    regression = {"total": result.testsRun, "passed": len(passed), "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped), "old_153_retained": old_retained,
                  "new_phase42_tests": sum(r["id"].startswith("tests.test_phase4_2.") for r in outcomes),
                  "network_attempts": attempts, "outcomes": outcomes}
    state.durable_json(directory / "regression_final.json", regression)
    config = trial.read_json(trial.CONFIG)
    trial.environment_guard(config)
    ledger = trial.read_json(config["ledger_path"])
    trial.validate_ledger(config, ledger)
    checkpoint = state.load(config["state_path"])
    launch = trial.read_json(directory / "cleanup_probe_launch.json")
    cleanup = trial.read_json(directory / "cleanup_probe_receipt.json")
    all_pass = result.wasSuccessful() and old_retained and not result.skipped and not attempts
    prior = trial.read_json(directory / "readiness.json") if (directory / "readiness.json").exists() else {}
    readiness = {**prior, "at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "regression_153_pass": old_retained,
                 "offline_guards_pass": all_pass, "regression_total": result.testsRun,
                 "new_guard_tests": regression["new_phase42_tests"], "scheduler_launch_pass": launch.get("state_lock_pass") and launch.get("pinned_code_pass"),
                 "automatic_stop_mechanism_offline_pass": cleanup["all_removed"],
                 "scheduler_installed": prior.get("scheduler_installed", False), "http_requests": 0, "protected_files": len(trial.read_json(config["protected_manifest"])["sha256"]),
                 "protected_evidence_unchanged": trial.protected_ok(config),
                 "state_initialized_empty_v2": checkpoint["schema_version"] == 2 and not checkpoint["stocks"] and not checkpoint["event_records"],
                 "state_initial_hash_unchanged": trial.digest(config["state_path"]) == config["initial_state_sha256"],
                 "claimed_attempts": sum(r["claimed"] for r in ledger["runs"]),
                 "network_capability": "NOT_YET_TESTED: first Yahoo request only on scheduled date",
                 "automations_assessment": {"official_documentation": "https://learn.chatgpt.com/docs/automations", "local_mode_available": True,
                     "worktree_option_exists": True, "strict_expiry_removal_not_proven": True,
                     "selection": "launchd selected for deterministic executable/path, tested one-shot removal and owned plist cleanup"},
                 "proof_files": [str(directory / name) for name in ("regression_153.json", "regression_final.json", "scheduler_probe.json", "cleanup_probe_launch.json", "cleanup_probe_receipt.json")],
                 "requirements": ["Mac powered on, logged in as UID 501, awake at 09:00 Brisbane", "Internet access; secure CA verification enabled", "Keep project, virtualenv, pinned code and trial files in place", "No automatic catchup or recovery; any blocked run requires manual review"],
                 "deadline_cleanup": "2026-11-07T09:30:00+10:00; cleanup only; zero Yahoo requests",
                 "sleep_policy": "No wakeup is configured. Calendar triggers coalesce on wake; expired/late captures are refused. Unregistration can only execute when Mac is running."}
    state.durable_json(directory / "readiness.json", readiness)
    trial.write_acceptance(config, ledger)
    print(json.dumps({k: v for k, v in readiness.items() if k not in ("automations_assessment", "proof_files")}, ensure_ascii=False, indent=2))
    return 0 if all_pass and cleanup["all_removed"] and launch.get("state_lock_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
