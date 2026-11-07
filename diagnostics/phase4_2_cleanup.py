"""Remove ONLY manifest-owned Phase 4.2 launchd jobs; never requests prices."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "phase4_2_trial"
PREFIX = "com.rui.bigtech.phase42."


def write_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp, path)
    fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def unregister(item, uid):
    label = item["label"]
    path = Path(item["installed_plist"])
    if not label.startswith(PREFIX) or path.name != label + ".plist":
        raise ValueError("Refusing non-owned schedule")
    target = f"gui/{uid}/{label}"
    result = subprocess.run(["/bin/launchctl", "bootout", target], capture_output=True, text=True, timeout=15)
    check = subprocess.run(["/bin/launchctl", "print", target], capture_output=True, text=True, timeout=15)
    absent = check.returncode == 113 and "Could not find service" in check.stderr
    owned = not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() == item["plist_sha256"]
    if absent and owned and path.exists():
        path.unlink()
    return {"label": label, "bootout_returncode": result.returncode, "bootout_stderr": result.stderr,
            "print_returncode": check.returncode, "print_stderr": check.stderr,
            "service_absent": absent, "owned_plist": owned, "plist_absent": not path.exists(),
            "removed": absent and owned and not path.exists()}


def main():
    manifest_path = Path(sys.argv[1]).resolve()
    scope, reason = sys.argv[2:4]
    if manifest_path not in ((TRIAL / "config/launchd_manifest.json").resolve(), (TRIAL / "preflight/cleanup_probe_manifest.json").resolve()):
        raise ValueError("Unrecognized manifest path")
    manifest = json.loads(manifest_path.read_text())
    if manifest["uid"] != os.getuid():
        raise ValueError("UID mismatch")
    time.sleep(1)
    selected = [item for item in manifest["jobs"] if scope == "all" or str(item["run"]) == scope]
    results = []
    for item in selected:
        try:
            results.append(unregister(item, manifest["uid"]))
        except Exception as exc:
            results.append({"label": item["label"], "removed": False, "error": f"{type(exc).__name__}: {exc}"})
    receipt = {"at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "reason": reason,
               "scope": scope, "http_requests": 0, "jobs": results,
               "all_removed": bool(results) and all(r["removed"] for r in results)}
    if manifest_path.name == "cleanup_probe_manifest.json":
        write_json(TRIAL / "preflight/cleanup_probe_receipt.json", receipt)
        return
    write_json(TRIAL / "acceptance" / ("stop_receipt.json" if scope == "all" else f"run_{scope}_cleanup.json"), receipt)
    from src import phase4_2 as trial, state
    ledger_path = TRIAL / "execution_ledger.json"
    if ledger_path.exists():
        with state.lock(ledger_path):
            ledger = trial.read_json(ledger_path)
            if scope == "all":
                if ledger["status"] not in trial.TERMINAL:
                    ledger.update(status="STOPPED", block_reason=reason)
                if (TRIAL / "acceptance/BLOCKED.json").exists():
                    ledger.update(status="BLOCKED", block_reason=trial.read_json(TRIAL / "acceptance/BLOCKED.json")["reason"])
                if not receipt["all_removed"]:
                    ledger.update(status="BLOCKED", block_reason="AUTOMATIC_STOP_FAILED: inspect stop receipt manually")
                for row in ledger["runs"]:
                    if not row["claimed"]:
                        row["result"] = "NOT_RUN_STOPPED"
                    elif row["result"] == "CLAIMED":
                        row.update(result="BLOCKED", error="Uncertain interrupted capture/commit; manual reconciliation required")
                state.durable_json(ledger_path, ledger)
            trial.write_acceptance(trial.read_json(trial.CONFIG), ledger)


if __name__ == "__main__":
    main()
