"""Small launchd supervisor. No networking here; timeout/exception stops all jobs."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "phase4_2_trial"


def main():
    run = sys.argv[1]
    stop_all = run == "deadline"
    reason = "DEADLINE_CLEANUP_ONLY" if stop_all else "RUN_FINISHED"
    try:
        if not stop_all:
            result = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "src.phase4_2", "--run", run],
                                    cwd=ROOT, timeout=600, check=False)
            ledger = json.loads((TRIAL / "execution_ledger.json").read_text())
            stop_all = result.returncode != 0 or ledger["status"] in ("COMPLETED", "STOPPED", "BLOCKED") or run == "5"
            reason = ledger.get("block_reason") or ledger["status"]
    except Exception as exc:
        stop_all = True
        reason = f"SUPERVISOR_ERROR: {type(exc).__name__}: {exc}; capture/commit may be uncertain; no retry"
        (TRIAL / "acceptance/BLOCKED.json").write_text(json.dumps({"at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "reason": reason, "no_automatic_retry": True}) + "\n")
    # The tested detached child survives LaunchOnlyOnce parent termination.
    # It verifies absence, removes installed plists, writes a durable stop receipt.
    subprocess.Popen([str(ROOT / ".venv/bin/python"), str(ROOT / "diagnostics/phase4_2_cleanup.py"),
                      str(TRIAL / "config/launchd_manifest.json"), "all" if stop_all else run, reason],
                     cwd=ROOT, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=open(TRIAL / "logs/cleanup.stdout.log", "a"),
                     stderr=open(TRIAL / "logs/cleanup.stderr.log", "a"))


if __name__ == "__main__":
    main()
