"""Explicitly authorized 2026-11-03 one-shot. Never re-arms the stopped trial."""
import argparse
import datetime as dt
import json
from pathlib import Path
import platform
import sys
import time

import market_calendar as calendar
from src import phase4, phase4_2 as trial, state

ROOT = trial.ROOT
DIRECTORY = ROOT / "phase4_2_manual_20261103"
IDENTITY = "phase4_2_manual_20261103"
AUTHORIZED_DATE = "2026-11-03"
TARGET_DATE = "2026-11-02"


def validate_date(now):
    if now.astimezone(trial.ZONE).date().isoformat() != AUTHORIZED_DATE:
        raise trial.GuardError("MANUAL_AUTHORIZATION_EXPIRED: only 2026-11-03 Brisbane")
    if calendar.latest_completed_session(now).isoformat() != TARGET_DATE:
        raise trial.GuardError("CALENDAR_TARGET_MISMATCH: one-shot targets completed 2026-11-02 session")


def prepare():
    validate_date(dt.datetime.now(dt.timezone.utc))
    if (DIRECTORY / "config.json").exists() or (DIRECTORY / "execution_ledger.json").exists():
        raise trial.GuardError("ONE_SHOT_ALREADY_PREPARED: never replace the ledger")
    before = trial.read_json(DIRECTORY / "preflight/before_patch.json")
    original = trial.read_json(ROOT / "phase4_2_trial/preflight/protected_manifest.json")
    hashes = {name: value for name, value in original["sha256"].items()
              if Path(name).name not in trial.IGNORED_EVIDENCE_BASENAMES}
    hashes.update(before["old_trial_sha256"])
    manifest_path = DIRECTORY / "protected_manifest.json"
    state.durable_json(manifest_path, {"sha256": hashes, "excluded_basenames": sorted(trial.IGNORED_EVIDENCE_BASENAMES),
                                       "source": "original historical hashes plus preserved stopped-trial evidence; no business rebaselining"})
    config = {"trial_id": IDENTITY, "authorized_brisbane_date": AUTHORIZED_DATE, "target_trading_date": TARGET_DATE,
              "maximum_attempts": 1, "mode": "USER_AUTHORIZED_MANUAL_ONE_SHOT_DRY_RUN", "scheduler_created": False,
              "authorization": "好的，请进行最小修复，然后执行一次今天的任务。",
              "original_schedule": "Original 09:00 trial remains BLOCKED and stopped; this is a separate later manual execution.",
              "protected_manifest": str(manifest_path), "protected_manifest_sha256": trial.digest(manifest_path),
              "python_version": platform.python_version(),
              "code_sha256": {name: trial.digest(ROOT / name) for name in
                              [*trial.read_json(ROOT / "phase4_2_trial/config/trial.json")["code_sha256"],
                               "diagnostics/run_phase4_2_once.py"]}}
    differences = trial.protected_differences(config)
    if differences:
        raise trial.GuardError("BUSINESS_EVIDENCE_CHANGED: " + json.dumps(differences))
    for name in ("state", "reports", "logs"):
        (DIRECTORY / name).mkdir(exist_ok=True)
    checkpoint = DIRECTORY / "state/monitor_state.json"
    value = state.migrate({"schema_version": 1, "rules_version": state.RULES_VERSION, "stocks": {}})[0]
    value["trial_id"] = IDENTITY
    state.initialize(checkpoint, value)
    config.update(state_path=str(checkpoint), initial_state_sha256=trial.digest(checkpoint))
    state.durable_json(DIRECTORY / "config.json", config)
    state.durable_json(DIRECTORY / "execution_ledger.json", {"trial_id": IDENTITY, "claimed": False, "status": "READY",
                         "config_sha256": trial.digest(DIRECTORY / "config.json"), "created_at_utc": trial.utc()})
    print(json.dumps({"prepared": True, "maximum_attempts": 1, "target": TARGET_DATE, "http_requests": 0}))


def verify(config, ledger):
    validate_date(dt.datetime.now(dt.timezone.utc))
    if (Path.cwd().resolve() != ROOT or sys.executable != str(ROOT / ".venv/bin/python")
            or platform.python_version() != config["python_version"] or config["trial_id"] != IDENTITY
            or config["state_path"] != str(DIRECTORY / "state/monitor_state.json")
            or ledger["trial_id"] != IDENTITY or ledger["config_sha256"] != trial.digest(DIRECTORY / "config.json")):
        raise trial.GuardError("ONE_SHOT_ENVIRONMENT_OR_CONFIG_MISMATCH")
    if ledger["claimed"] or ledger["status"] != "READY":
        raise trial.GuardError("ONE_SHOT_ALREADY_CLAIMED: no automatic retry, including uncertain crashes")
    for name, expected in config["code_sha256"].items():
        if trial.digest(ROOT / name) != expected:
            raise trial.GuardError("PINNED_CODE_CHANGED: " + name)
    differences = trial.protected_differences(config)
    if differences:
        raise trial.GuardError("PROTECTED_EVIDENCE_CHANGED: " + json.dumps(differences))
    checkpoint = state.load(config["state_path"])
    if (trial.digest(config["state_path"]) != config["initial_state_sha256"] or checkpoint["schema_version"] != 2
            or checkpoint.get("trial_id") != IDENTITY or checkpoint["stocks"] or checkpoint["event_records"]):
        raise trial.GuardError("ONE_SHOT_CHECKPOINT_NOT_PRISTINE")
    if phase4.collector.REQUEST_START_INTERVAL_SECONDS != 5 or phase4.collector.BATCH_EXTRA_WAIT_SECONDS != 30:
        raise trial.GuardError("COLLECTION_POLICY_CHANGED")


def run():
    config = trial.read_json(DIRECTORY / "config.json")
    path = DIRECTORY / "execution_ledger.json"
    with state.lock(path):
        ledger = trial.read_json(path)
        verify(config, ledger)
        # Check availability before claiming. Phase4 takes the same state lock
        # throughout collection and commit; this ledger lock excludes duplicate runs.
        with state.lock(config["state_path"]):
            state.load(config["state_path"])
        ledger.update(claimed=True, status="CLAIMED", started_at_utc=trial.utc(),
                      actual_http_request_count=None, outcome="UNCERTAIN_UNTIL_COMPLETION_RECEIPT")
        state.durable_json(path, ledger)  # durable BEFORE DNS or HTTP
        started = time.monotonic()
        try:
            result = phase4.execute(state_path=Path(config["state_path"]), output_dir=DIRECTORY / "reports", mode="LIVE_FETCH")
            preserved = trial.protected_ok(config)
            summary = {"trial_id": IDENTITY, "mode": config["mode"], "dry_run": True,
                       "execution_kind": "MANUAL_ONE_SHOT_NOT_THE_09_00_SCHEDULED_RUN", "scheduled_run_reclassified": False,
                       "baseline": "TRIAL_FIRST_BASELINE" if result.get("success_count") == 9 else "INCOMPLETE_BASELINE",
                       "target_trading_date": TARGET_DATE, "state_path": config["state_path"],
                       "result": result["result"] if preserved else "STATE_ERROR",
                       "protected_business_and_old_trial_unchanged": preserved, "protected_differences": trial.protected_differences(config),
                       "actual_http_request_count": result["actual_http_request_count"], "http_200_count": result.get("http_200_count", 0),
                       "rate_limited": result.get("rate_limited", False), "timing_pass": result.get("timing_pass"),
                       "request_intervals": result.get("request_intervals", []), "collection_results": result.get("collection_results", []),
                       "stocks": result["stocks"], "confirmed_events": result["new_observation_events"],
                       "pending_review_events": result.get("pending_review_events", []),
                       "state_hash_before": result["state_hash_before"], "state_hash_after": result["state_hash_after"],
                       "state_updated": result["state_updated"], "detailed_report": result["report_file"],
                       "collection_report": result.get("collection_report"), "error": result["error"],
                       "started_at_utc": ledger["started_at_utc"], "finished_at_utc": trial.utc(),
                       "elapsed_seconds": time.monotonic() - started, "scheduler_created": False,
                       "cross_day_live_validation": "PENDING", "automatic_catchup": "NOT_VALIDATED"}
            state.durable_json(DIRECTORY / "summary.json", summary)
            (DIRECTORY / "summary.md").write_text("# 今日人工授权单次 DRY_RUN\n\n"
                + f"Result: {summary['result']}; target: {TARGET_DATE}; HTTP: {summary['actual_http_request_count']}; "
                + f"elapsed: {summary['elapsed_seconds']:.3f}s\n\n原09:00试运行保持BLOCKED；本次不计为按时自动运行。\n\n"
                + phase4.monitor.markdown({"mode": config["mode"], "stocks": summary["stocks"]}))
            ledger.update(status=summary["result"], finished_at_utc=summary["finished_at_utc"],
                          actual_http_request_count=summary["actual_http_request_count"], outcome="RECORDED",
                          state_hash_after=summary["state_hash_after"], summary=str(DIRECTORY / "summary.json"))
            state.durable_json(path, ledger)
            print(json.dumps({k: summary[k] for k in ("result", "actual_http_request_count", "http_200_count", "rate_limited", "elapsed_seconds", "state_updated")}, ensure_ascii=False))
            return 0 if summary["result"] in ("PASS", "PASS_PROVISIONAL") else 2
        except BaseException as exc:
            ledger.update(status="BLOCKED", error=f"{type(exc).__name__}: {exc}", finished_at_utc=trial.utc(),
                          outcome="UNCERTAIN: inspect saved collection evidence; never automatically repeat")
            state.durable_json(path, ledger)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    args = parser.parse_args()
    return prepare() if args.action == "prepare" else run()


if __name__ == "__main__":
    raise SystemExit(main())
