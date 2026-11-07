"""Offline-first CLI: .venv/bin/python -m src.monitor [--input prices.json]."""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import platform

import market_calendar as calendar
import test_yahoo_nine as phase2
from src import indicators, signals, state

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports/yahoo_nine_prices_20261030_141537.json"


def read_input(path):
    evidence = json.loads(path.read_text())
    if evidence.get("schema_version") != 1 or not isinstance(evidence.get("stocks"), dict) or not set(evidence["stocks"]).issubset(state.SYMBOLS):
        raise ValueError("INPUT_SCHEMA_ERROR: expected Phase 2 nine-stock evidence")
    diagnostic_path = Path(evidence["diagnostic_file"])
    if not diagnostic_path.exists():
        diagnostic_path = path.parent / diagnostic_path.name
    diagnostic = json.loads(diagnostic_path.read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != diagnostic["price_evidence_sha256"]:
        raise ValueError("INPUT_INTEGRITY_ERROR: Phase 2 price evidence hash mismatch")
    if diagnostic.get("schema_version") != 1:
        raise ValueError("INPUT_SCHEMA_ERROR: unsupported diagnostic version")
    identities = {s["symbol"]: s for s in diagnostic["stocks"]}
    if set(identities) != set(state.SYMBOLS) or len(diagnostic["stocks"]) != 9:
        raise ValueError("INPUT_SCHEMA_ERROR: diagnostic universe mismatch")
    return evidence, identities


def validated_prices(symbol, stock, diagnostic):
    if diagnostic["http_status"] != 200 or not diagnostic["data_quality_pass"]:
        raise ValueError("DATA_QUALITY_ERROR: Phase 2 result did not pass")
    if stock.get("symbol") != symbol or not stock.get("identity_validated"):
        raise ValueError("IDENTITY_MISMATCH")
    as_of = dt.datetime.fromisoformat(stock["as_of_utc"])
    target = calendar.latest_completed_session(as_of).isoformat()
    rows = stock["rows"]
    # Reconstruct the actual Phase 2 Chart shape and rerun existing identity and
    # calendar/array/price validators, rather than trusting saved PASS flags.
    result = {"meta": diagnostic["identity"], "timestamp": [r["timestamp"] for r in rows],
              "indicators": {"adjclose": [{"adjclose": [r["adjclose"] for r in rows]}],
                             "quote": [{"close": [r["close"] for r in rows]}]}}
    checked = phase2.new_row(symbol, diagnostic["batch"])
    phase2.analyze_payload(checked, {"chart": {"error": None, "result": [result]}}, as_of)
    if not checked["data_quality_pass"]:
        raise ValueError(json.dumps(checked["errors"], ensure_ascii=False))
    completed = []
    excluded = []
    for row in rows:
        day = dt.datetime.fromtimestamp(row["timestamp"], calendar.NY).date()
        bounds = calendar.session_bounds(day)
        if row["trading_date"] != day.isoformat() or not bounds:
            raise ValueError("DATA_QUALITY_ERROR: evidence timestamp/date mismatch")
        complete = as_of >= bounds[1]
        if row["regular_session_completed"] != complete:
            raise ValueError("DATA_QUALITY_ERROR: incorrect session completion flag")
        allowed_flags = [] if complete else ["INCOMPLETE_SESSION_EXCLUDED"]
        if row["flags"] != allowed_flags:
            raise ValueError("DATA_QUALITY_ERROR: unexpected evidence flags")
        (completed if complete else excluded).append(row)
    pairs = [(r["trading_date"], r["adjclose"]) for r in completed]
    indicators.validate_series(pairs, target)
    return completed, target, checked, excluded


def process_symbol(symbol, stock, diagnostic, previous, significant_pp):
    completed, target, checked, excluded = validated_prices(symbol, stock, diagnostic)
    if previous and target < previous["trading_date"]:
        raise ValueError("STALE_DATA: cannot move persisted state backward")
    pairs = [(r["trading_date"], r["adjclose"]) for r in completed]
    metrics = indicators.calculate(pairs, target, allow_short=checked.get("short_history_explained", False))
    prices = dict(pairs)
    changes = state.revisions(previous, prices)
    event = signals.transition(previous, metrics, bool(changes), significant_pp)
    warnings = ["YAHOO_ONLY: history is not independently price-verified", "TECHNICAL_OBSERVATION_ONLY: investment value not assessed"]
    anomaly = None
    if symbol == "SPCX":
        anomaly = {"date": "2026-06-16", "yahoo_close_reported": 211.39,
                   "nasdaq_close_reported": 201.80, "field": "Close",
                   "source": "User-provided historical conflict; not independently verified in Phase 3",
                   "adjclose_conflict_established": False,
                   "observed_yahoo_close": next((r["close"] for r in completed if r["trading_date"] == "2026-06-16"), None),
                   "date_is_window_high": metrics["highest_date"] == "2026-06-16"}
        warnings += ["YAHOO_ONLY/HISTORICAL_ANOMALY_UNVERIFIED: all SPCX observations provisional",
                     "Close discrepancy cannot establish the Adj Close correction or its effect on tiers",
                     "SMA200: INSUFFICIENT_HISTORY" if metrics["sma200"] is None else "IPO history independently dated; prices remain Yahoo-only"]
    observation = {"symbol": symbol, "close": completed[-1]["close"], **metrics, **event,
                   "data_quality": "PASS_PROVISIONAL" if symbol == "SPCX" else "PASS",
                   "warnings": warnings, "historical_anomaly": anomaly,
                   "historical_revision_count": len(changes), "historical_revision_examples": changes[:10],
                   "excluded_incomplete_dates": [r["trading_date"] for r in excluded],
                   "source_as_of_utc": stock["as_of_utc"], "source": "YAHOO_CHART_ADJCLOSE",
                   "rules_version": indicators.RULES_VERSION, "independently_price_verified": False}
    updated = {**observation, "history_prices": prices, "history_fingerprint": state.fingerprint(prices)}
    return observation, updated


def markdown(report):
    lines = ["# Local technical observations", "", f"Mode: {report['mode']}; captured market history, not a new quote. No investment-value rating.", "",
             "| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |",
             "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|"]
    def fmt(value):
        return "N/A" if value is None else f"{value:.4f}"
    for row in report["stocks"]:
        if row["change_event"] == "DATA_ERROR":
            lines.append(f"| {row['symbol']} | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | DATA_ERROR | FAIL |")
            continue
        lines.append(f"| {row['symbol']} | {row['trading_date']} | {fmt(row['close'])} | {fmt(row['adjclose'])} | {row['window_samples']} | {fmt(row['highest_adjclose'])} | {row['highest_date']} | {row['drawdown'] * 100:.2f}% | {fmt(row['rsi14'])} | {fmt(row['sma50'])} | {fmt(row['sma200'])} | {row['watch_tier']} | {row['change_event']} | {row['data_quality']} |")
    lines += ["", "Warnings and errors:", ""]
    for row in report["stocks"]:
        lines.append(f"- {row['symbol']}: " + (row.get("error_message") or "; ".join(row["warnings"])))
    lines += ["", "SPCX historical conflict: user-reported 2026-06-16 Yahoo Close $211.39 vs Nasdaq Close $201.80; Close only, not an established Adj Close discrepancy. All SPCX observations are provisional.", ""]
    return "\n".join(lines)


def _run_unlocked(input_path=DEFAULT_INPUT, state_path=ROOT / "state/monitor_state.json", output_dir=ROOT / "reports", significant_pp=signals.SIGNIFICANT_DEEPENING_PP, mode="OFFLINE_SNAPSHOT", expected_target=None):
    input_path, state_path, output_dir = Path(input_path), Path(state_path), Path(output_dir)
    # Read state before any mutation; corruption must never turn into a new baseline.
    previous = state.load(state_path)
    signals.transition(None, {"drawdown": 0, "trading_date": "validation"}, significant_pp=significant_pp)
    evidence, diagnostic = read_input(input_path)
    next_state = copy.deepcopy(previous)
    report = {"schema_version": 1, "mode": mode, "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "input_file": str(input_path.resolve()), "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
              "rules_version": indicators.RULES_VERSION, "significant_deepening_pp": significant_pp,
              "numeric_policy": "Float64; abs_tol=1e-8, rel_tol=1e-10 for overlap revisions; display-only rounding; RSI flat=50",
              "python_version": platform.python_version(), "calendar_version": calendar.CALENDAR_VERSION,
              "state_file": str(state_path.resolve()), "stocks": []}
    changed = False
    report["new_observation_events"] = []
    for symbol in state.SYMBOLS:
        try:
            observation, updated = process_symbol(symbol, evidence["stocks"][symbol], diagnostic[symbol], previous["stocks"].get(symbol), significant_pp)
            if expected_target is not None and observation["trading_date"] != expected_target:
                raise ValueError("STALE_DATA: live target mismatch; no candidate update")
            if observation["change_event"] != "NO_CHANGE":
                semantic = {key: observation[key] for key in ("symbol", "trading_date", "change_event", "crossed_thresholds_this_run", "rules_version")}
                if observation["change_event"] == "HISTORICAL_REVISION":
                    semantic["revision_fingerprint"] = updated["history_fingerprint"]
                event_id = state.fingerprint(semantic)
                observation["event_id"] = event_id
                ledger = next_state.setdefault("event_records", {})
                if event_id not in ledger:
                    ledger[event_id] = {**semantic, "data_quality": observation["data_quality"]}
                    if observation["change_event"] not in ("FIRST_BASELINE", "HISTORICAL_REVISION"):
                        report["new_observation_events"].append(ledger[event_id])
            if previous["stocks"].get(symbol) is None or observation["change_event"] != "NO_CHANGE" or updated["history_fingerprint"] != previous["stocks"][symbol]["history_fingerprint"]:
                next_state["stocks"][symbol] = updated
                changed = True
            report["stocks"].append(observation)
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            report["stocks"].append({"symbol": symbol, "change_event": "DATA_ERROR", "data_quality": "FAIL", "error_message": str(exc), "previous_state_preserved": symbol in previous["stocks"]})
    report["success_count"] = sum(r["change_event"] != "DATA_ERROR" for r in report["stocks"])
    report["failure_count"] = 9 - report["success_count"]
    report["state_updated"] = changed
    if changed:
        state.save(state_path, next_state)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Add suffix if two legitimate runs finish within one second, never overwrite.
    name = "monitor_indicators_" + dt.datetime.now(phase2.BRISBANE).strftime("%Y%m%d_%H%M%S")
    base = output_dir / name
    suffix = 1
    while base.with_suffix(".json").exists():
        base = output_dir / f"{name}_{suffix}"
        suffix += 1
    report["report_file"] = str(base.with_suffix(".json").resolve())
    phase2.atomic_json(base.with_suffix(".json"), report)
    md_path = base.with_suffix(".md")
    md_path.write_text(markdown(report))
    print(json.dumps({key: report[key] for key in ("mode", "success_count", "failure_count", "state_updated", "report_file")}, ensure_ascii=False))
    return report


def run(input_path=DEFAULT_INPUT, state_path=ROOT / "state/monitor_state.json", output_dir=ROOT / "reports", significant_pp=signals.SIGNIFICANT_DEEPENING_PP, mode="OFFLINE_SNAPSHOT"):
    with state.lock(state_path):
        return _run_unlocked(input_path, state_path, output_dir, significant_pp, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--input", type=Path, default=None)
    group.add_argument("--fetch", action="store_true")
    parser.add_argument("--state", type=Path, default=ROOT / "state/monitor_state.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--significant-pp", type=float, default=signals.SIGNIFICANT_DEEPENING_PP)
    args = parser.parse_args()
    try:
        with state.lock(args.state):
            state.load(args.state)
            input_path = args.input or DEFAULT_INPUT
            if args.fetch:
                fetched = phase2.run(output_dir=args.output_dir)
                input_path = Path(fetched["price_evidence_file"])
            report = _run_unlocked(input_path, args.state, args.output_dir, args.significant_pp, "LIVE_FETCH" if args.fetch else "OFFLINE_SNAPSHOT")
        return int(report["failure_count"] > 0)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
