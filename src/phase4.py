"""Isolated DRY_RUN acceptance runner. Never writes the Phase 3 formal state."""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
import contextlib

import market_calendar as calendar
import test_yahoo_nine as collector
from src import monitor, state, indicators

ROOT = monitor.ROOT
FORMAL = ROOT / "state/monitor_state.json"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


@contextlib.contextmanager
def audited_lock(path, report):
    with state.lock(path):
        try:
            yield
        finally:
            report["state_hash_at_lock_release"] = file_hash(path)


def execute(input_path=None, state_path=ROOT/"phase4_trial/state/monitor_state.json", output_dir=ROOT/"phase4_trial/reports", mode="OFFLINE_REPLAY"):
    state_path, output_dir = Path(state_path), Path(output_dir)
    if state_path.resolve() == FORMAL.resolve():
        raise state.StateError("Phase 4 refuses the formal Phase 3 state path")
    start = time.monotonic()
    before, formal_before = file_hash(state_path), file_hash(FORMAL)
    report = {"schema_version": 1, "dry_run": True, "mode": mode,
              "started_at_utc": collector.utc_now().isoformat(), "rules_version": indicators.RULES_VERSION,
              "code_sha256": state.fingerprint({str(p.relative_to(ROOT)):file_hash(p) for p in sorted((ROOT/"src").glob("*.py"))}),
              "state_file": str(state_path.resolve()), "state_hash_before": before,
              "formal_state_hash_before": formal_before, "state_updated": False,
              "actual_http_request_count": 0, "stocks": [], "new_observation_events": [],
              "state_read": False, "state_saved": False, "recovery": "NO_AUTOMATIC_RECOVERY",
              "error": None, "result": "EXECUTION_ERROR"}
    try:
        state.load(state_path)  # Missing checkpoint is not a fresh run.
        output_dir.mkdir(parents=True, exist_ok=True)
        with audited_lock(state_path, report):
            previous = state.load(state_path)
            report["state_commit_version_before"] = previous.get("commit_version", 0)
            report["state_read"] = True
            # Guard hash must be sampled after lock acquisition for this transaction.
            report["state_hash_before"] = file_hash(state_path)
            if mode == "LIVE_FETCH":
                fetched = collector.run(output_dir=output_dir/"collection", execution_context="phase4-unsandboxed")
                input_path = Path(fetched["price_evidence_file"])
                report.update({key:fetched[key] for key in ("actual_http_request_count", "http_200_count", "rate_limited", "request_intervals", "timing_pass")})
                report["collection_report"] = fetched["report_file"]
                report["collection_results"] = [{key:row.get(key) for key in ("symbol", "http_status", "request_start_utc", "request_end_utc", "elapsed_seconds", "error_category", "error_message", "retry_after")} for row in fetched["stocks"]]
            if input_path is None:
                input_path = monitor.DEFAULT_INPUT
            report["input_file"] = str(Path(input_path).resolve())
            # Offline data remains assessed at its capture time. Only LIVE_FETCH
            # claims freshness; revalidate against current completed session too.
            if mode == "LIVE_FETCH":
                expected = calendar.latest_completed_session(collector.utc_now()).isoformat()
                report["target_trading_date"] = expected
                # Newly fetched metadata normally already has this target;
                # reject stale captures at per-symbol validation, not by skipping rows.
                result = monitor._run_unlocked(input_path, state_path, output_dir, mode=mode, expected_target=expected)
            else:
                result = monitor._run_unlocked(input_path, state_path, output_dir, mode=mode)
            report["monitor_report"] = result["report_file"]
            report["stocks"] = result["stocks"]
            report["new_observation_events"] = result["new_observation_events"]
            report["pending_review_events"] = result["pending_review_events"]
            report["migration"] = result["migration"]
            report["event_model_version"] = result["event_model_version"]
            report["state_saved"] = True
            report["state_commit_version_after"] = state.load(state_path).get("commit_version", 0)
            report["success_count"], report["failure_count"] = result["success_count"], result["failure_count"]
            if "target_trading_date" not in report:
                report["target_trading_date"] = sorted({r["trading_date"] for r in result["stocks"] if "trading_date" in r})
            report["result"] = "RATE_LIMITED" if report.get("rate_limited") else (
                "PARTIAL_SUCCESS" if 0 < result["success_count"] < 9 else (
                    "DATA_ERROR" if result["success_count"] == 0 else (
                        "PASS_PROVISIONAL" if any(r["data_quality"] == "PASS_PROVISIONAL" for r in result["stocks"]) else "PASS")))
    except (state.StateError, OSError) as exc:
        report["result"] = "STATE_ERROR"
        report["error"] = f"{type(exc).__name__}: {exc}"
        if 'MISSING_EXISTING_STATE' in str(exc):
            report['recovery']={'status':'MISSING_EXISTING_STATE','validated_backup_inventory':state.list_backups(state_path),
                                'automatic_selection':False,'action':'Explicitly select verified backup or obtain manual recovery evidence; never reset.'}
    except (ValueError, KeyError, TypeError) as exc:
        report["result"] = "DATA_ERROR"
        report["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        report["result"] = "EXECUTION_ERROR"
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["state_hash_after"] = report.get("state_hash_at_lock_release", file_hash(state_path))
    report['state_missing_after'] = report['state_hash_after'] is None
    report["state_updated"] = report["state_read"] and not report['state_missing_after'] and report["state_hash_after"] != report["state_hash_before"]
    report["formal_state_hash_after"] = file_hash(FORMAL)
    report["formal_state_unchanged"] = formal_before == report["formal_state_hash_after"]
    report["backup_files"] = [str(p) for p in sorted(state_path.with_name(state_path.name+".backups").glob("*.json"))]
    report["finished_at_utc"] = collector.utc_now().isoformat()
    report["elapsed_seconds"] = time.monotonic() - start
    output_dir.mkdir(parents=True, exist_ok=True)
    name = "phase4_e2e_" + dt.datetime.now(collector.BRISBANE).strftime("%Y%m%d_%H%M%S_%f")
    path = output_dir/(name+".json")
    collector.atomic_json(path, report)
    md = [f"# Phase 4 {mode} — {report['result']}", "", f"DRY_RUN; requests={report['actual_http_request_count']}; state_updated={report['state_updated']}; elapsed={report['elapsed_seconds']:.3f}s", "", f"Error: {report['error']}", ""]
    if report["stocks"]:
        md.append(monitor.markdown({"mode":mode,"stocks":report["stocks"]}))
    path.with_suffix(".md").write_text("\n".join(md))
    report["report_file"] = str(path)
    print(json.dumps({"result":report["result"],"report_file":str(path),"state_updated":report["state_updated"]}))
    return report


def replay(input_path=monitor.DEFAULT_INPUT, output_dir=ROOT/"phase4_trial/replay"):
    output_dir = Path(output_dir)
    if (output_dir/"state.json").exists():
        raise ValueError("Replay state exists; select a fresh replay directory")
    output_dir.mkdir(parents=True,exist_ok=True)
    state.initialize(output_dir/"state.json")  # --replay explicitly requests a new isolated history run.
    evidence, identities = monitor.read_input(Path(input_path))
    common = set.intersection(*[{r["trading_date"] for r in evidence["stocks"][s]["rows"] if r["regular_session_completed"]} for s in state.SYMBOLS])
    dates = sorted(common)[-5:]
    results = []
    for target in dates:
        directory = output_dir/target
        directory.mkdir(parents=True, exist_ok=True)
        truncated = copy.deepcopy(evidence)
        as_of = (calendar.session_bounds(dt.date.fromisoformat(target))[1]+dt.timedelta(minutes=1)).astimezone(dt.timezone.utc).isoformat()
        for stock in truncated["stocks"].values():
            stock["rows"] = [r for r in stock["rows"] if r["trading_date"] <= target]
            stock["as_of_utc"] = as_of
        source = directory/"prices.json"
        diagnostic = directory/"diagnostic.json"
        truncated["diagnostic_file"] = str(diagnostic.resolve())
        collector.atomic_json(source, truncated)
        collector.atomic_json(diagnostic, {"schema_version":1,"price_evidence_sha256":file_hash(source),"stocks":list(identities.values())})
        report = execute(source, output_dir/"state.json", directory, "OFFLINE_REPLAY")
        repeated = execute(source, output_dir/"state.json", directory, "OFFLINE_REPLAY")
        assert report.get("success_count") == 9
        assert not repeated["state_updated"] and not repeated["new_observation_events"]
        results.append({"target":target,"report":report["report_file"],"repeat_report":repeated["report_file"],"idempotent":True,"events":report["new_observation_events"]})
    summary = {"mode":"OFFLINE_REPLAY","not_live_discoveries":True,"days":results,"final_state":str(output_dir/"state.json")}
    collector.atomic_json(output_dir/"summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fetch", action="store_true")
    group.add_argument("--replay", action="store_true")
    group.add_argument("--recover-backup", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--state", type=Path, default=ROOT/"phase4_trial/state/monitor_state.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT/"phase4_trial/reports")
    args = parser.parse_args()
    if args.state.resolve() == FORMAL.resolve():
        parser.error("Formal Phase 3 state is read-only in Phase 4")
    if args.recover_backup:
        print(json.dumps(state.recover(args.state, args.recover_backup)))
        return 0
    if args.replay:
        replay(args.input or monitor.DEFAULT_INPUT, args.output_dir)
        return 0
    result = execute(args.input, args.state, args.output_dir, "LIVE_FETCH" if args.fetch else "OFFLINE_REPLAY")
    return int(result["result"] not in ("PASS","PASS_PROVISIONAL"))


if __name__ == "__main__":
    raise SystemExit(main())
