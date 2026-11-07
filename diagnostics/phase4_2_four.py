"""Four finite launchd runs, 2026-11-04..07 10:00 Brisbane; no trading."""
import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import platform
import plistlib
import ssl
import subprocess
import sys
import tempfile
import time

import market_calendar as calendar
import test_yahoo_nine as collector
from src import monitor, observations, phase4_2 as common, state
from diagnostics.phase4_2_cleanup import unregister

ROOT = common.ROOT
BASE = ROOT / "phase4_2_four_20261104"
CONFIG = BASE / "config/trial.json"
LEDGER = BASE / "execution_ledger.json"
IDENTITY = "phase4_2_four_20261104_20261107"
PREFIX = "com.rui.bigtech.phase42.four20261104."
PLAN = tuple({"run": i, "scheduled_brisbane": f"2026-11-{i+3:02d}T10:00:00+10:00",
              "target_date": f"2026-11-{i+2:02d}"} for i in range(1, 5))
DEADLINE = "2026-11-07T10:30:00+10:00"
MODULE = "diagnostics.phase4_2_four"


def block(reason):
    state.durable_json(BASE / "acceptance/BLOCKED.json", {"at_utc": common.utc(), "reason": reason, "automatic_retry": False})


def validate_ledger(config, ledger):
    if (ledger.get("trial_id") != IDENTITY or ledger.get("config_sha256") != common.digest(CONFIG)
            or [r.get("plan") for r in ledger.get("runs", [])] != list(PLAN)
            or ledger.get("status") not in {"ARMED", *common.TERMINAL}
            or len(ledger["runs"]) != 4 or any(type(r.get("claimed")) is not bool for r in ledger["runs"])):
        raise common.GuardError("LEDGER_INTEGRITY_ERROR")


def check_environment(config):
    if (Path.cwd().resolve() != ROOT or config["root"] != str(ROOT) or config["trial_id"] != IDENTITY
            or config["state_path"] != str(BASE / "state/monitor_state.json") or config["plan"] != list(PLAN)
            or sys.executable != str(ROOT / ".venv/bin/python") or platform.python_version() != config["python_version"]):
        raise common.GuardError("ENVIRONMENT_OR_PATH_MISMATCH")
    if common.digest(BASE / "config/launchd_manifest.json") != config["launchd_manifest_sha256"]:
        raise common.GuardError("SCHEDULE_MANIFEST_CHANGED")
    for name, expected in config["code_sha256"].items():
        if common.digest(ROOT / name) != expected:
            raise common.GuardError("PINNED_CODE_CHANGED: " + name)
    differences = common.protected_differences(config)
    if differences:
        raise common.GuardError("PROTECTED_EVIDENCE_CHANGED: " + json.dumps(differences, ensure_ascii=False))
    if collector.REQUEST_START_INTERVAL_SECONDS != 5 or collector.BATCH_EXTRA_WAIT_SECONDS != 30:
        raise common.GuardError("COLLECTION_POLICY_CHANGED")


def guard(config, ledger, checkpoint, number, now):
    validate_ledger(config, ledger)
    if ledger["status"] in common.TERMINAL or (BASE / "acceptance/BLOCKED.json").exists():
        raise common.GuardError("TRIAL_TERMINAL_OR_BLOCKED")
    if number not in range(1, 5) or sum(r["claimed"] for r in ledger["runs"]) >= 4:
        raise common.GuardError("ATTEMPT_LIMIT: maximum four, failures count")
    row = ledger["runs"][number-1]
    if row["claimed"]:
        raise common.GuardError("DUPLICATE_CLAIM: never request again")
    if any(r["claimed"] and r["result"] == "CLAIMED" for r in ledger["runs"]):
        raise common.GuardError("UNCERTAIN_CAPTURE_OR_COMMIT: manual reconciliation required")
    scheduled = dt.datetime.fromisoformat(row["plan"]["scheduled_brisbane"])
    local = now.astimezone(common.ZONE)
    if local.date() != scheduled.date() or not scheduled <= local < scheduled + dt.timedelta(minutes=15):
        raise common.GuardError("OUTSIDE_WINDOW: scheduled date 10:00–10:14:59 Brisbane only")
    target = row["plan"]["target_date"]
    if calendar.latest_completed_session(now).isoformat() != target:
        raise common.GuardError("CALENDAR_TARGET_MISMATCH")
    if any(not r["claimed"] or r["result"] != "SUCCESS" for r in ledger["runs"][:number-1]):
        raise common.GuardError("CATCHUP_REQUIRED: missed or failed scheduled day")
    previous_date = config["baseline"]["trading_date"] if number == 1 else PLAN[number-2]["target_date"]
    expected_hash = config["initial_state_sha256"] if number == 1 else ledger["runs"][number-2]["state_hash_after"]
    if common.digest(config["state_path"]) != expected_hash:
        raise common.GuardError("STATE_CONTINUITY_ERROR")
    if checkpoint.get("schema_version") != 2 or checkpoint.get("trial_id") != IDENTITY or set(checkpoint["stocks"]) != set(state.SYMBOLS):
        raise common.GuardError("STATE_IDENTITY_ERROR: existing nine-stock v2 state required")
    for symbol in state.SYMBOLS:
        if (checkpoint["stocks"][symbol]["trading_date"] != previous_date
                or observations.missing_sessions(previous_date, target) or target <= previous_date):
            raise common.GuardError("CATCHUP_REQUIRED: " + symbol)


def request_guard(number):
    seen = set()

    def check(row):
        ledger = common.read_json(LEDGER)
        claim = ledger["runs"][number-1]
        if ((BASE / "acceptance/BLOCKED.json").exists() or ledger["status"] != "ARMED"
                or not claim["claimed"] or claim["result"] != "CLAIMED"):
            raise common.GuardError("PERSISTENT_BLOCK_OR_CHANGED_CLAIM")
        if dt.datetime.now(common.ZONE).date().isoformat() != PLAN[number-1]["scheduled_brisbane"][:10]:
            raise common.GuardError("REQUEST_DATE_EXPIRED")
        if row["symbol"] not in state.SYMBOLS or row["symbol"] in seen or len(seen) >= 9:
            raise common.GuardError("DUPLICATE_OR_UNEXPECTED_SYMBOL")
        seen.add(row["symbol"])

    return check


def summarize(config, ledger):
    stop = common.read_json(BASE / "acceptance/stop_receipt.json") if (BASE / "acceptance/stop_receipt.json").exists() else None
    success = [r for r in ledger["runs"] if r["result"] == "SUCCESS"]
    terminal = ledger["status"] in common.TERMINAL
    try:
        differences = common.protected_differences(config)
    except Exception as exc:
        differences = [{"error": f"{type(exc).__name__}: {exc}"}]
    final = bool(stop and stop["all_removed"] and terminal)
    result = ("PASS_PROVISIONAL" if final and len(success) == 4 and not differences else
              "FAIL" if terminal and not success else "PARTIAL" if success or terminal else "PENDING")
    report = {"trial_id": IDENTITY, "dry_run": True, "updated_at_utc": common.utc(), "final": final,
              "result": result, "status": ledger["status"], "block_reason": ledger.get("block_reason"),
              "baseline": config["baseline"], "state_path": config["state_path"], "max_attempts": 4,
              "claimed_attempts": sum(r["claimed"] for r in ledger["runs"]),
              "actual_http_request_count": None if any(r["claimed"] and r.get("network_outcome") != "RECORDED" for r in ledger["runs"]) else sum(r.get("actual_http_request_count", 0) for r in ledger["runs"]),
              "runs": ledger["runs"], "stop_receipt": stop, "protected_differences": differences,
              "cross_day_live_validation": "PASS" if len(success) == 4 else "PARTIAL" if success else "PENDING",
              "live_threshold_detection": common.live_threshold_status(ledger["runs"]),
              "live_revisions_observed": any(r.get("revision_count", 0) for r in ledger["runs"]),
              "unattended_catchup_recovery": "NOT_VALIDATED", "spcx": "PASS_PROVISIONAL / YAHOO_ONLY/HISTORICAL_ANOMALY_UNVERIFIED",
              "scheduler": "launchd: four collection jobs and one zero-request deadline summary/cleanup job",
              "deadline_cleanup_brisbane": DEADLINE}
    state.durable_json(BASE / "acceptance/summary.json", report)
    lines = ["# Phase 4.2 四次有限期试运行总结", "", f"状态：{ledger['status']}；结果：{result}；最终总结：{final}。",
             "", "仅真实日志计为完成；2026-11-03人工采集是继承基线，不计入四次自动运行。",
             "", "| Run | Brisbane 执行时间 | 目标美股交易日 | HTTP次数 | 状态更新 | 结果 |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['plan']['run']} | {r['plan']['scheduled_brisbane']} | {r['plan']['target_date']} | {r.get('actual_http_request_count', '—')} | {r.get('state_updated', '—')} | {r['result']} |" for r in ledger["runs"]]
    lines += ["", f"基线交易日：{config['baseline']['trading_date']}；基线来源：{config['baseline']['source_state']}。",
              "", "最多四次认领，失败计数；不重试、不自动补跑；严重异常提前停止全部本次调度。",
              "Mac须开机、登录、联网并在10:00保持唤醒。迟到超过15分钟拒绝采集；关机期间不能清理，恢复后拒绝过期采集并清理。",
              "周六第4次结束后生成最终总结并清理；10:30仅清理和汇总的任务不请求Yahoo。",
              "SPCX为PASS_PROVISIONAL，历史异常未独立核实；未观测到真实触档时不声称已发生。", ""]
    for row in ledger["runs"]:
        if row.get("stocks"):
            lines += [f"## Run {row['plan']['run']}", "", monitor.markdown({"mode": "FOUR_DAY_LIVE_DRY_RUN", "stocks": row["stocks"]}), "",
                      f"状态哈希：{row.get('state_hash_before')} → {row.get('state_hash_after')}。", ""]
    (BASE / "acceptance/summary.md").write_text("\n".join(lines) + "\n")
    return report


def execute(number):
    config = common.read_json(CONFIG)
    with state.lock(LEDGER):
        ledger = common.read_json(LEDGER)
        try:
            check_environment(config)
            state.load(config["state_path"])
            with state.lock(config["state_path"]):
                checkpoint = state.load(config["state_path"])
                guard(config, ledger, checkpoint, number, dt.datetime.now(dt.timezone.utc))
                row = ledger["runs"][number-1]
                row.update(claimed=True, result="CLAIMED", started_at_utc=common.utc(),
                           state_hash_before=common.digest(config["state_path"]), commit_version_before=checkpoint["commit_version"],
                           network_outcome="UNCERTAIN_UNTIL_COMPLETION_RECEIPT")
                state.durable_json(LEDGER, ledger)
                fetched = collector.run(output_dir=BASE / f"collection/run_{number}", execution_context="phase4.2-four-launchd",
                                        request_guard=request_guard(number))
                row.update({key: fetched[key] for key in ("actual_http_request_count", "http_200_count", "rate_limited", "request_intervals", "timing_pass", "price_evidence_file")})
                row.update(collection_report=fetched["report_file"], collection_results=fetched["stocks"],
                           price_evidence_sha256=common.digest(fetched["price_evidence_file"]), network_outcome="RECORDED")
                state.durable_json(LEDGER, ledger)
                check_environment(config)  # before any market-state commit
                if (BASE / "acceptance/BLOCKED.json").exists():
                    raise common.GuardError("PERSISTENT_BLOCK_BEFORE_COMMIT")
                result = monitor._run_unlocked(Path(fetched["price_evidence_file"]), Path(config["state_path"]), BASE / f"reports/run_{number}",
                                               mode="FOUR_DAY_LIVE_DRY_RUN", expected_target=row["plan"]["target_date"])
                after = state.load(config["state_path"])
                row.update(stocks=result["stocks"], monitor_report=result["report_file"], confirmed_events=result["new_observation_events"],
                           pending_review_events=result["pending_review_events"], event_ids=sorted(after["event_records"]),
                           revision_count=sum(r.get("historical_revision_count", 0) for r in result["stocks"]),
                           state_hash_after=common.digest(config["state_path"]), commit_version_after=after["commit_version"],
                           state_updated=result["state_updated"], ended_at_utc=common.utc(),
                           result="RATE_LIMITED" if fetched["rate_limited"] else "SUCCESS" if result["success_count"] == 9 and fetched["timing_pass"] else "PARTIAL_SUCCESS" if result["success_count"] else "DATA_ERROR")
                if row["result"] != "SUCCESS":
                    ledger.update(status="BLOCKED", block_reason="DATA_FAILURE_OR_CATCHUP_REQUIRED: no automatic retry")
                    block(ledger["block_reason"])
                elif number == 4:
                    ledger["status"] = "COMPLETED"
        except Exception as exc:
            ledger.update(status="BLOCKED", block_reason=f"{type(exc).__name__}: {exc}")
            block(ledger["block_reason"])
            if number in range(1, 5):
                row = ledger["runs"][number-1]
                if row["claimed"] and row["result"] == "CLAIMED":
                    row.update(result="STATE_ERROR" if isinstance(exc, state.StateError) else "EXECUTION_ERROR", error=str(exc), ended_at_utc=common.utc(), requires_manual_reconciliation=True)
                elif not row["claimed"]:
                    row.update(result="BLOCKED", pre_request_rejected=True, error=str(exc), actual_http_request_count=0, ended_at_utc=common.utc())
        state.durable_json(LEDGER, ledger)
        summarize(config, ledger)
        print(json.dumps({"status": ledger["status"], "run": number, "block_reason": ledger.get("block_reason")}))
        return 2 if ledger["status"] == "BLOCKED" else 0


def launch_job(label, arguments, when=None, immediate=False):
    job = {"Label": label, "ProgramArguments": [str(ROOT / ".venv/bin/python"), "-B", "-m", MODULE, *arguments],
           "WorkingDirectory": str(ROOT), "EnvironmentVariables": {"PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(BASE / "preflight/tmp")},
           "RunAtLoad": immediate, "KeepAlive": False, "LaunchOnlyOnce": True, "AbandonProcessGroup": True,
           "StandardOutPath": str(BASE / f"logs/{label}.stdout.log"), "StandardErrorPath": str(BASE / f"logs/{label}.stderr.log")}
    if when:
        stamp = dt.datetime.fromisoformat(when)
        job["StartCalendarInterval"] = {"Month": stamp.month, "Day": stamp.day, "Hour": stamp.hour, "Minute": stamp.minute}
    return job


def prepare():
    if CONFIG.exists() or LEDGER.exists():
        raise common.GuardError("EXISTING_TRIAL: no replacement or reset")
    manual = ROOT / "phase4_2_manual_20261103"
    parent = common.read_json(manual / "summary.json")
    source = Path(parent["state_path"])
    source_hash = common.digest(source)
    seed = state.load(source)
    if (parent["result"] not in ("PASS", "PASS_PROVISIONAL") or source_hash != parent["state_hash_after"]
            or set(seed["stocks"]) != set(state.SYMBOLS) or {s["trading_date"] for s in seed["stocks"].values()} != {"2026-11-02"}):
        raise common.GuardError("INVALID_MANUAL_BASELINE")
    for directory in ("config", "state", "collection", "reports", "logs", "acceptance", "preflight/tmp"):
        (BASE / directory).mkdir(parents=True, exist_ok=True)
    hashes = common.read_json(manual / "protected_manifest.json")["sha256"]
    hashes.update({str(p.relative_to(ROOT)): common.digest(p) for p in manual.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.name not in common.IGNORED_EVIDENCE_BASENAMES})
    protected = BASE / "config/protected_manifest.json"
    state.durable_json(protected, {"sha256": hashes, "excluded_basenames": sorted(common.IGNORED_EVIDENCE_BASENAMES)})
    seed = copy.deepcopy(seed)
    seed["trial_id"] = IDENTITY
    baseline = {"source_state": str(source), "source_state_sha256": source_hash, "source_commit_version": seed["commit_version"],
                "trading_date": "2026-11-02", "capture_summary": str(manual / "summary.json"), "capture_finished_at_utc": parent["finished_at_utc"],
                "kind": "VERIFIED_MANUAL_LIVE_BASELINE_NOT_AN_AUTOMATED_RUN"}
    seed["baseline_provenance"] = baseline
    checkpoint = BASE / "state/monitor_state.json"
    state.initialize(checkpoint, seed)
    jobs = []
    for plan in (*PLAN, {"run": "deadline", "scheduled_brisbane": DEADLINE}):
        number = plan["run"]
        label = PREFIX + ("deadline" if number == "deadline" else f"run{number}")
        path = BASE / "config" / (label + ".plist")
        path.write_bytes(plistlib.dumps(launch_job(label, ["supervise", str(number)], plan["scheduled_brisbane"])))
        jobs.append({"label": label, "run": number, "source_plist": str(path), "installed_plist": str(Path.home() / "Library/LaunchAgents" / path.name),
                     "plist_sha256": common.digest(path), "scheduled_brisbane": plan["scheduled_brisbane"], "collection_allowed": number != "deadline"})
    manifest = BASE / "config/launchd_manifest.json"
    state.durable_json(manifest, {"trial_id": IDENTITY, "uid": os.getuid(), "jobs": jobs})
    sources = [*common.read_json(manual / "config.json")["code_sha256"], "diagnostics/phase4_2_four.py"]
    config = {"trial_id": IDENTITY, "root": str(ROOT), "python_version": platform.python_version(), "plan": list(PLAN),
              "max_attempts": 4, "state_path": str(checkpoint), "initial_state_sha256": common.digest(checkpoint), "baseline": baseline,
              "protected_manifest": str(protected), "protected_manifest_sha256": common.digest(protected),
              "launchd_manifest_sha256": common.digest(manifest), "code_sha256": {name: common.digest(ROOT / name) for name in sources}}
    state.durable_json(CONFIG, config)
    state.durable_json(LEDGER, {"trial_id": IDENTITY, "status": "ARMED", "config_sha256": common.digest(CONFIG), "created_at_utc": common.utc(),
                                "runs": [{"plan": dict(p), "claimed": False, "result": "PENDING"} for p in PLAN]})
    check_environment(config)
    summarize(config, common.read_json(LEDGER))
    print(json.dumps({"prepared": True, "collection_jobs": 4, "deadline_cleanup_only": DEADLINE, "baseline_date": baseline["trading_date"], "http_requests": 0}))


def clean(scope, reason, probe=False):
    time.sleep(1)
    if not probe and scope == "all" and common.read_json(LEDGER)["status"] == "ARMED":
        block(reason)  # Also stops any orphan worker before its next HTTP/commit.
    manifest = common.read_json(BASE / ("preflight/probe_manifest.json" if probe else "config/launchd_manifest.json"))
    results = []
    for item in manifest["jobs"]:
        if not probe and scope != "all" and str(item["run"]) != scope:
            continue
        expected_parent = BASE / "preflight" if probe else Path.home() / "Library/LaunchAgents"
        if not item["label"].startswith(PREFIX) or Path(item["installed_plist"]).parent != expected_parent:
            raise common.GuardError("REFUSE_NON_OWNED_JOB")
        try:
            results.append(unregister(item, manifest["uid"]))
        except Exception as exc:
            results.append({"label": item["label"], "removed": False, "error": str(exc)})
    receipt = {"at_utc": common.utc(), "scope": scope, "reason": reason, "http_requests": 0, "jobs": results,
               "all_removed": bool(results) and all(r["removed"] for r in results)}
    destination = BASE / ("preflight/probe_cleanup.json" if probe else "acceptance/stop_receipt.json" if scope == "all" else f"acceptance/run_{scope}_cleanup.json")
    state.durable_json(destination, receipt)
    if probe:
        return
    if scope != "all" and not receipt["all_removed"]:
        block("JOB_CLEANUP_FAILED: inspect run cleanup receipt")
        detached_cleanup("all", "JOB_CLEANUP_FAILED")
        return
    with state.lock(LEDGER):
        ledger = common.read_json(LEDGER)
        if scope == "all":
            if ledger["status"] not in common.TERMINAL:
                ledger.update(status="STOPPED", block_reason=reason)
            if (BASE / "acceptance/BLOCKED.json").exists():
                ledger.update(status="BLOCKED", block_reason=common.read_json(BASE / "acceptance/BLOCKED.json")["reason"])
            if not receipt["all_removed"]:
                ledger.update(status="BLOCKED", block_reason="AUTOMATIC_STOP_FAILED: inspect stop receipt")
            for row in ledger["runs"]:
                if row["claimed"] and row["result"] == "CLAIMED":
                    row.update(result="BLOCKED", error="Uncertain interrupted capture/commit; do not retry")
                elif not row["claimed"] and row["result"] == "PENDING":
                    row["result"] = "NOT_RUN_STOPPED"
            state.durable_json(LEDGER, ledger)
        summarize(common.read_json(CONFIG), ledger)


def detached_cleanup(scope, reason, probe=False):
    subprocess.Popen([str(ROOT / ".venv/bin/python"), "-B", "-m", MODULE, "probe-cleanup" if probe else "cleanup", scope, reason],
                     cwd=ROOT, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=open(BASE / "logs/cleanup.stdout.log", "a"), stderr=open(BASE / "logs/cleanup.stderr.log", "a"))


def supervise(number):
    scope, reason = "all", "DEADLINE_SUMMARY_ONLY"
    try:
        if number != "deadline":
            result = subprocess.run([str(ROOT / ".venv/bin/python"), "-B", "-m", MODULE, "run", number], cwd=ROOT, timeout=600)
            ledger = common.read_json(LEDGER)
            scope = "all" if result.returncode or ledger["status"] in common.TERMINAL or number == "4" else number
            reason = ledger.get("block_reason") or ledger["status"]
    except Exception as exc:
        reason = f"SUPERVISOR_ERROR: {type(exc).__name__}: {exc}"
        block(reason)
    finally:
        detached_cleanup(scope, reason)


def probe():
    config = common.read_json(CONFIG)
    check_environment(config)
    ssl.create_default_context()
    with state.lock(LEDGER), state.lock(config["state_path"]):
        ledger = common.read_json(LEDGER)
        validate_ledger(config, ledger)
        checkpoint = state.load(config["state_path"])
        if any(r["claimed"] for r in ledger["runs"]) or common.digest(config["state_path"]) != config["initial_state_sha256"]:
            raise common.GuardError("PROBE_MUST_NOT_CLAIM_OR_CHANGE_STATE")
        state.durable_json(BASE / "preflight/probe_launch.json", {"at_utc": common.utc(), "cwd": str(Path.cwd()), "python": sys.executable,
                           "state_schema": checkpoint["schema_version"], "state_sha256": common.digest(config["state_path"]),
                           "state_lock": True, "ledger_lock": True, "tls_ca_loaded": True, "http_requests": 0})
    detached_cleanup("all", "OFFLINE_LAUNCH_AND_STOP_PROOF", probe=True)


def install():
    config = common.read_json(CONFIG)
    check_environment(config)
    ledger = common.read_json(LEDGER)
    validate_ledger(config, ledger)
    tests = common.read_json(BASE / "preflight/regression.json")
    if tests["failed"] or tests["errors"] or tests["skipped"] or not tests["original_153_retained"] or tests["network_attempts"]:
        raise common.GuardError("OFFLINE_REGRESSION_FAILED")
    if time.timezone != -36000 or time.daylight or dt.datetime.now(common.ZONE) >= dt.datetime.fromisoformat(PLAN[0]["scheduled_brisbane"]):
        raise common.GuardError("SYSTEM_TIMEZONE_OR_INSTALLATION_WINDOW_MISMATCH")
    if ledger["status"] != "ARMED" or any(r["claimed"] for r in ledger["runs"]) or common.digest(config["state_path"]) != config["initial_state_sha256"]:
        raise common.GuardError("TRIAL_ALREADY_STARTED_OR_CHANGED")
    items = common.read_json(BASE / "config/launchd_manifest.json")["jobs"]
    for item in items:
        query = subprocess.run(["/bin/launchctl", "print", f"gui/{os.getuid()}/{item['label']}"], capture_output=True, text=True)
        if query.returncode != 113 or "Could not find service" not in query.stderr or os.path.lexists(item["installed_plist"]):
            raise common.GuardError("EXISTING_JOB: " + item["label"])
        if common.digest(item["source_plist"]) != item["plist_sha256"]:
            raise common.GuardError("SCHEDULE_DEFINITION_CHANGED")
    probes = []
    for kind in ("probe-idle", "probe-active"):
        label = PREFIX + kind
        path = BASE / "preflight" / (label + ".plist")
        if path.exists():
            raise common.GuardError("EXISTING_PROBE: inspect before reusing")
        path.write_bytes(plistlib.dumps(launch_job(label, ["probe"], immediate=kind == "probe-active")))
        probes.append({"label": label, "run": kind, "installed_plist": str(path), "plist_sha256": common.digest(path)})
    state.durable_json(BASE / "preflight/probe_manifest.json", {"uid": os.getuid(), "jobs": probes})
    try:
        for item in probes:
            subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", item["installed_plist"]], check=True, capture_output=True, text=True)
        deadline = time.monotonic() + 25
        while not (BASE / "preflight/probe_cleanup.json").exists() and time.monotonic() < deadline:
            time.sleep(0.25)
        if not common.read_json(BASE / "preflight/probe_cleanup.json")["all_removed"]:
            raise common.GuardError("OFFLINE_AUTOMATIC_STOP_FAILED")
    except Exception:
        for item in probes:
            unregister(item, os.getuid())
        raise
    installed = []
    try:
        for item in items:
            destination = Path(item["installed_plist"])
            destination.parent.mkdir(exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(Path(item["source_plist"]).read_bytes()); handle.flush(); os.fsync(handle.fileno())
            installed.append(item)
            subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(destination)], check=True, capture_output=True, text=True)
            query = subprocess.run(["/bin/launchctl", "print", f"gui/{os.getuid()}/{item['label']}"], check=True, capture_output=True, text=True)
            (BASE / "preflight" / (item["label"] + ".launchctl.txt")).write_text(query.stdout)
        state.durable_json(BASE / "preflight/installation.json", {"at_utc": common.utc(), "installed": True, "jobs": items, "http_requests": 0})
    except Exception:
        state.durable_json(BASE / "preflight/installation_rollback.json", {"jobs": [unregister(item, os.getuid()) for item in installed]})
        raise
    print(json.dumps({"installed": True, "collection_jobs": 4, "deadline_summary_only_jobs": 1, "http_requests": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "install", "run", "supervise", "cleanup", "probe", "probe-cleanup"))
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    if (BASE / "preflight/tmp").is_dir():
        tempfile.tempdir = str(BASE / "preflight/tmp")
        os.environ["TMPDIR"] = tempfile.tempdir
    if args.action == "run":
        return execute(int(args.args[0]))
    if args.action == "supervise":
        return supervise(args.args[0])
    if args.action in ("cleanup", "probe-cleanup"):
        return clean(args.args[0], args.args[1], probe=args.action == "probe-cleanup")
    return {"prepare": prepare, "install": install, "probe": probe}[args.action]()


if __name__ == "__main__":
    raise SystemExit(main())
