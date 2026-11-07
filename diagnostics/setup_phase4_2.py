"""Prepare/verify/install the explicitly authorized finite local trial only."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import time

from src import phase4_2 as trial, state

ROOT, TRIAL = trial.ROOT, trial.TRIAL
PREFIX = "com.rui.bigtech.phase42."


def job(label, run, when):
    return {"Label": label, "ProgramArguments": [str(ROOT / ".venv/bin/python"), str(ROOT / "diagnostics/run_phase4_2.py"), str(run)],
            "WorkingDirectory": str(ROOT), "EnvironmentVariables": {"PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"},
            "StartCalendarInterval": {"Month": when.month, "Day": when.day, "Hour": when.hour, "Minute": when.minute},
            "RunAtLoad": False, "KeepAlive": False, "LaunchOnlyOnce": True, "AbandonProcessGroup": True,
            "StandardOutPath": str(TRIAL / f"logs/{run}.stdout.log"), "StandardErrorPath": str(TRIAL / f"logs/{run}.stderr.log")}


def prepare():
    if trial.CONFIG.exists() or (TRIAL / "execution_ledger.json").exists() or (TRIAL / "state/monitor_state.json").exists():
        raise ValueError("Trial already prepared: refusing replacement or reinitialization")
    for name in ("config", "state", "collection", "reports", "logs", "acceptance"):
        (TRIAL / name).mkdir(exist_ok=True)
    value = state.migrate({"schema_version": 1, "rules_version": state.RULES_VERSION, "stocks": {}})[0]
    value["trial_id"] = trial.TRIAL_ID
    checkpoint = TRIAL / "state/monitor_state.json"
    state.initialize(checkpoint, value)
    items = []
    for run in (*trial.PLAN, {"run": "deadline", "scheduled_brisbane": "2026-11-07T09:30:00+10:00"}):
        number = run["run"]
        label = PREFIX + (f"run{number}-2026110{int(number)+2}" if number != "deadline" else "deadline-20261107")
        path = TRIAL / "config" / (label + ".plist")
        path.write_bytes(plistlib.dumps(job(label, number, dt.datetime.fromisoformat(run["scheduled_brisbane"]))))
        items.append({"label": label, "run": number, "source_plist": str(path),
                      "installed_plist": str(Path.home() / "Library/LaunchAgents" / path.name),
                      "plist_sha256": trial.digest(path), "scheduled_brisbane": run["scheduled_brisbane"],
                      "collection_allowed": number != "deadline"})
    manifest = TRIAL / "config/launchd_manifest.json"
    state.durable_json(manifest, {"uid": os.getuid(), "trial_id": trial.TRIAL_ID, "jobs": items})
    sources = sorted((ROOT / "src").glob("*.py")) + [ROOT / name for name in ("market_calendar.py", "test_yahoo_nine.py", "test_yahoo_nvda.py", "diagnostics/run_phase4_2.py", "diagnostics/phase4_2_cleanup.py", "diagnostics/setup_phase4_2.py")]
    config = {"trial_id": trial.TRIAL_ID, "root": str(ROOT), "python": str(ROOT / ".venv/bin/python"),
              "python_version": platform.python_version(), "state_path": str(checkpoint),
              "ledger_path": str(TRIAL / "execution_ledger.json"), "plan": list(trial.PLAN),
              "symbols": list(state.SYMBOLS), "max_attempts": 5, "deadline_brisbane": "2026-11-07",
              "start_window_minutes": 15, "request_start_interval_seconds": 5, "batch_extra_wait_seconds": 30,
              "initial_state_sha256": trial.digest(checkpoint), "launchd_manifest_sha256": trial.digest(manifest),
              "protected_manifest": str(TRIAL / "preflight/protected_manifest.json"),
              "code_sha256": {str(p.relative_to(ROOT)): trial.digest(p) for p in sources}}
    state.durable_json(trial.CONFIG, config)
    ledger = {"trial_id": trial.TRIAL_ID, "config_sha256": trial.digest(trial.CONFIG), "status": "ARMED",
              "initialized_at_utc": trial.utc(), "runs": [{"plan": dict(p), "claimed": False, "result": "PENDING"} for p in trial.PLAN]}
    state.durable_json(TRIAL / "execution_ledger.json", ledger)
    trial.write_acceptance(config, ledger)
    print(json.dumps({"prepared": True, "state": str(checkpoint), "code_files_pinned": len(sources), "http_requests": 0}))


def install():
    config = trial.read_json(trial.CONFIG)
    trial.environment_guard(config)
    readiness = trial.read_json(TRIAL / "preflight/readiness.json")
    proof = trial.read_json(TRIAL / "preflight/cleanup_probe_receipt.json")
    if not all(readiness.get(k) for k in ("regression_153_pass", "offline_guards_pass")) or not proof["all_removed"]:
        raise ValueError("A-C must pass before schedule creation")
    if time.timezone != -36000 or time.daylight:
        raise ValueError("launchd calendar requires this Mac's Brisbane/AEST system timezone")
    manifest = trial.read_json(TRIAL / "config/launchd_manifest.json")
    if trial.digest(TRIAL / "config/launchd_manifest.json") != config["launchd_manifest_sha256"]:
        raise ValueError("Launch manifest changed")
    if dt.datetime.now(trial.ZONE) >= dt.datetime.fromisoformat(trial.PLAN[0]["scheduled_brisbane"]):
        raise ValueError("Refuse late initial installation")
    ledger = trial.read_json(TRIAL / "execution_ledger.json")
    trial.validate_ledger(config, ledger)
    if any(r["claimed"] for r in ledger["runs"]) or ledger["status"] != "ARMED":
        raise ValueError("Refuse installation after trial has started/stopped")
    for item in manifest["jobs"]:
        target = f"gui/{os.getuid()}/{item['label']}"
        check = subprocess.run(["/bin/launchctl", "print", target], capture_output=True, text=True)
        if check.returncode != 113 or "Could not find service" not in check.stderr or Path(item["installed_plist"]).exists():
            raise ValueError("Pre-existing schedule requires manual inspection: " + item["label"])
        if trial.digest(item["source_plist"]) != item["plist_sha256"]:
            raise ValueError("Schedule definition changed")
    installed = []
    try:
        for item in manifest["jobs"]:
            dest = Path(item["installed_plist"])
            dest.parent.mkdir(exist_ok=True)
            # Exclusive creation prevents overwriting any concurrently created job.
            with dest.open("xb") as handle:
                handle.write(Path(item["source_plist"]).read_bytes()); handle.flush(); os.fsync(handle.fileno())
            installed.append(item)
            subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(dest)], check=True, capture_output=True, text=True)
            check = subprocess.run(["/bin/launchctl", "print", f"gui/{os.getuid()}/{item['label']}"], check=True, capture_output=True, text=True)
            (TRIAL / "preflight" / (item["label"] + ".launchctl.txt")).write_text(check.stdout)
    except Exception:
        # Import is local and rollback only covers exclusively created owned jobs.
        from diagnostics.phase4_2_cleanup import unregister
        rollback = [unregister(item, os.getuid()) for item in installed]
        state.durable_json(TRIAL / "preflight/installation_rollback.json", {"jobs": rollback})
        raise
    readiness.update(scheduler_installed=True, installed_at_utc=trial.utc(), jobs=manifest["jobs"],
                     system_timezone=list(time.tzname), system_utc_offset_seconds=-time.timezone)
    state.durable_json(TRIAL / "preflight/readiness.json", readiness)
    trial.write_acceptance(config, ledger)
    print(json.dumps({"installed": True, "collection_jobs": 5, "cleanup_only_jobs": 1, "http_requests": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "install"))
    args = parser.parse_args()
    return prepare() if args.action == "prepare" else install()


if __name__ == "__main__":
    main()
