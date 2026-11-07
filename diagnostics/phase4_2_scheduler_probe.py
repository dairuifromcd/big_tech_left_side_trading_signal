"""Offline launchd capability probe: no networking, no market state writes."""
import datetime as dt
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time


def main():
    output, label, plist = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    if sys.argv[1] in ("launch", "launch-cleanup"):
        import market_calendar
        from src import state
        ssl.create_default_context()  # Validate local CA loading only; no connection.
        extra = {}
        if sys.argv[1] == "launch-cleanup":
            from src import phase4_2 as trial
            config = trial.read_json(trial.CONFIG)
            trial.environment_guard(config)
            with state.lock(trial.TRIAL / "execution_ledger.json"):
                checkpoint = state.load(config["state_path"])
                with state.lock(config["state_path"]):
                    trial.validate_ledger(config, trial.read_json(config["ledger_path"]))
                    extra = {"persistent_state_path": config["state_path"], "state_schema": checkpoint["schema_version"],
                             "state_sha256": trial.digest(config["state_path"]), "ledger_lock_pass": True,
                             "state_lock_pass": True, "pinned_code_pass": True, "no_attempt_claimed": True}
        output.write_text(json.dumps({"launched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                                      "python": sys.version, "executable": sys.executable,
                                      "cwd": os.getcwd(), "uid": os.getuid(),
                                      "project_import": True, "tls_ca_loaded": True,
                                      "http_requests": 0, **extra}, indent=2))
        args = ([sys.executable, str(Path(__file__).with_name("phase4_2_cleanup.py")), sys.argv[5], "all", "OFFLINE_CLEANUP_PROOF"]
                if sys.argv[1] == "launch-cleanup" else
                [sys.executable, str(Path(__file__).resolve()), "cleanup", str(output), label, str(plist)])
        subprocess.Popen(args,
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    time.sleep(1)
    target = f"gui/{os.getuid()}/{label}"
    remove = subprocess.run(["/bin/launchctl", "bootout", target], capture_output=True, text=True)
    check = subprocess.run(["/bin/launchctl", "print", target], capture_output=True, text=True)
    result = json.loads(output.read_text())
    result.update(bootout_returncode=remove.returncode, bootout_stderr=remove.stderr,
                  print_returncode=check.returncode, print_stderr=check.stderr,
                  automatic_unregistration_verified=remove.returncode in (0, 3) and check.returncode == 113 and "Could not find service" in check.stderr,
                  cleanup_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    if result["automatic_unregistration_verified"]:
        plist.unlink()
    result["plist_removed"] = not plist.exists()
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
