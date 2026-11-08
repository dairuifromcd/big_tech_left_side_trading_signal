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
from src import indicators, signals, state, observations

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports/yahoo_nine_prices_20261030_141537.json"


class CatchupRequired(ValueError):
    def __init__(self,symbol,dates):
        self.symbol,self.missing_sessions=symbol,dates
        super().__init__(f"CATCHUP_REQUIRED: {symbol}; MISSING_SESSIONS={','.join(dates)}; previous checkpoint retained")


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


def process_symbol(symbol, stock, diagnostic, previous, significant_pp, *, event_context=None):
    completed, target, checked, excluded = validated_prices(symbol, stock, diagnostic)
    if previous and target < previous["trading_date"]:
        raise ValueError("STALE_DATA: cannot move persisted state backward")
    missing=observations.missing_sessions(previous['trading_date'],target) if previous else []
    if missing:
        raise CatchupRequired(symbol,missing)
    pairs = [(r["trading_date"], r["adjclose"]) for r in completed]
    metrics = indicators.calculate(pairs, target, allow_short=checked.get("short_history_explained", False))
    prices = dict(pairs)
    price_fingerprint = state.fingerprint(prices)
    if previous and price_fingerprint in previous.get("rejected_snapshot_fingerprints", []):
        raise ValueError("REJECTED_REVISION_SNAPSHOT: explicit review rejected this evidence; old valid state retained")
    closes = {r["trading_date"]: r["close"] for r in completed}
    identity = {key: diagnostic["identity"].get(key) for key in (
        "symbol", "longName", "instrumentType", "exchangeName", "fullExchangeName", "currency", "exchangeTimezoneName")}
    previous = copy.deepcopy(previous)
    # A v1 record can be enriched only from the identical saved capture, never
    # by pretending newly revised Close/identity values were previous evidence.
    if (previous and not previous.get("history_closes") and prices == previous["history_prices"]
            and previous.get("source_as_of_utc") == stock["as_of_utc"]
            and previous.get("close") == completed[-1]["close"]):
        previous["history_closes"] = closes
        previous["identity_snapshot"] = identity
        previous["comparison_evidence_hydrated_from_identical_capture"] = True
    model = observations.evaluate(symbol, pairs, closes, identity, previous, significant_pp, event_context=event_context)
    changes = model["revision_observation"]["raw_differences"]
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
    observation = {"symbol": symbol, "close": completed[-1]["close"], **metrics, **model,
                   "data_quality": "PASS_PROVISIONAL" if symbol == "SPCX" else "PASS",
                   "warnings": warnings, "historical_anomaly": anomaly,
                   "historical_revision_count": len(changes), "historical_revision_examples": changes[:10],
                   "excluded_incomplete_dates": [r["trading_date"] for r in excluded],
                   "source_as_of_utc": stock["as_of_utc"], "source": "YAHOO_CHART_ADJCLOSE",
                   "rules_version": indicators.RULES_VERSION, "event_model_version": state.EVENT_MODEL_VERSION,
                   "independently_price_verified": False}
    updated = {**observation, "history_prices": prices, "history_closes": closes,
               "identity_snapshot": identity, "history_fingerprint": price_fingerprint}
    updated["comparison_evidence_fingerprint"] = state.fingerprint({"closes": closes, "identity": identity})
    if previous:
        for key in ("legacy_triggered_thresholds", "migration_ambiguities", "rejected_snapshot_fingerprints"):
            if key in previous:
                updated[key] = copy.deepcopy(previous[key])
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
    lines += ["", "Daily movement and cumulative unconfirmed anchor scope:", "",
              "| Symbol | Daily drawdown change (pp) | New deepening today | Cumulative anchor depth (pp) | Raw candidate | Status | Confirmed |",
              "|---|---:|---|---:|---|---|---|"]
    for row in report["stocks"]:
        if row["change_event"] == "DATA_ERROR":continue
        lines.append("| "+" | ".join(str(row.get(k,"N/A")) for k in ('symbol','daily_drawdown_change_pp','daily_new_deepening','cumulative_anchor_deepening_pp','raw_market_candidate_type','event_status','candidate_confirmed'))+" |")
    lines += ["", "Warnings and errors:", ""]
    for row in report["stocks"]:
        lines.append(f"- {row['symbol']}: " + (row.get("error_message") or "; ".join(row["warnings"])))
    lines += ["", "SPCX historical conflict: user-reported 2026-06-16 Yahoo Close $211.39 vs Nasdaq Close $201.80; Close only, not an established Adj Close discrepancy. All SPCX observations are provisional.", ""]
    return "\n".join(lines)


def _run_unlocked(input_path=DEFAULT_INPUT, state_path=ROOT / "state/monitor_state.json", output_dir=ROOT / "reports", significant_pp=signals.SIGNIFICANT_DEEPENING_PP, mode="OFFLINE_SNAPSHOT", expected_target=None):
    input_path, state_path, output_dir = Path(input_path), Path(state_path), Path(output_dir)
    if state_path.resolve() == (ROOT / "state/monitor_state.json").resolve():
        raise state.StateError("ISOLATION_ERROR: Phase 4.1 requires an isolated state copy; formal v1 remains read-only")
    # Read state before any mutation; corruption must never turn into a new baseline.
    original = state.load(state_path)
    previous, migration = state.migrate(original)
    signals.transition(None, {"drawdown": 0, "trading_date": "validation"}, significant_pp=significant_pp)
    evidence, diagnostic = read_input(input_path)
    next_state = copy.deepcopy(previous)
    report = {"schema_version": 1, "mode": mode, "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "input_file": str(input_path.resolve()), "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
              "rules_version": indicators.RULES_VERSION, "significant_deepening_pp": significant_pp,
              "numeric_policy": "Float64; abs_tol=1e-8, rel_tol=1e-10 for overlap revisions; display-only rounding; RSI flat=50",
              "python_version": platform.python_version(), "calendar_version": calendar.CALENDAR_VERSION,
              "state_file": str(state_path.resolve()), "stocks": []}
    report["migration"] = migration
    report["schema_version"] = 2
    report["event_model_version"] = state.EVENT_MODEL_VERSION
    # A completely failed data run must not commit even a schema migration.
    # Successful candidate processing or explicit migrate_path can commit it.
    changed = False
    report["new_observation_events"] = []
    report["pending_review_events"] = []
    for symbol in state.SYMBOLS:
        try:
            symbol_candidate = copy.deepcopy(next_state)
            if mode=='ARCHIVED_CATCHUP':
                from src.catchup import validate_archive
                validate_archive(evidence['stocks'][symbol],diagnostic[symbol])
            observation, updated = process_symbol(symbol, evidence["stocks"][symbol], diagnostic[symbol], previous["stocks"].get(symbol), significant_pp,
                                                  event_context=previous.get("event_records",{}))
            if expected_target is not None and observation["trading_date"] != expected_target:
                raise ValueError("STALE_DATA: live target mismatch; no candidate update")
            proposed = list(observation["market_events"])
            revision = observation["revision_observation"]
            if revision["detected"]:
                proposed.append({"symbol": symbol, "trading_date": observation["trading_date"],
                                 "event_type": "REVISION_OBSERVATION", "threshold": None,
                                 "status": "PENDING_REVIEW" if revision["requires_review"] else "CONFIRMED",
                                 "reason": "History revision fact; does not confirm a market threshold",
                                 "evidence": {"revision_observation": revision,
                                              "previous_valid_stock": copy.deepcopy(previous["stocks"].get(symbol)),
                                              "snapshot_fingerprint": updated["history_fingerprint"]}})
            event_ids = []
            for candidate in proposed:
                candidate.setdefault("symbol", symbol)
                candidate.setdefault("trading_date", observation["trading_date"])
                candidate.setdefault("rules_version", indicators.RULES_VERSION)
                candidate.setdefault("evidence", {})["snapshot_fingerprint"] = updated["history_fingerprint"]
                candidate["data_quality"] = observation["data_quality"]
                candidate['origin_mode'] = mode
                event_id, new = state.register_event(symbol_candidate, candidate)
                event_ids.append(event_id)
            ledger = symbol_candidate["event_records"]
            confirmed = set(previous["stocks"].get(symbol, {}).get("confirmed_thresholds", []))
            confirmed.update(e["threshold"] for e in ledger.values() if e["symbol"] == symbol
                             and e["event_type"] in ("THRESHOLD_CROSSING", "LEGACY_THRESHOLD_REVIEW")
                             and e["status"] == "CONFIRMED" and e["threshold"] is not None)
            pending = [i for i,e in ledger.items() if e["symbol"] == symbol and e["status"] == "PENDING_REVIEW"]
            for current in (observation, updated):
                current["confirmed_thresholds"] = sorted(confirmed)
                current["triggered_thresholds"] = sorted(confirmed)
                current["threshold_state"]["confirmed"] = sorted(confirmed)
                current["threshold_state"]["pending_event_ids"] = sorted(pending)
                current["event_ids"] = event_ids
                current["revision_review_event_ids"] = sorted(i for i in pending if ledger[i]["event_type"] == "REVISION_OBSERVATION")
            old_stock = previous["stocks"].get(symbol)
            enrichment = old_stock is not None and (not old_stock.get("history_closes") or not old_stock.get("identity_snapshot"))
            ledger_changed = ledger != next_state["event_records"]
            if old_stock is None or enrichment or observation["change_event"] not in ("NO_CHANGE", "PENDING_REVIEW") or updated["history_fingerprint"] != old_stock["history_fingerprint"] or ledger_changed:
                symbol_candidate["stocks"][symbol] = updated
                state.validate_v2(symbol_candidate)
                new_ids = ledger.keys() - next_state["event_records"].keys()
                report["new_observation_events"].extend(copy.deepcopy(ledger[i]) for i in sorted(new_ids)
                    if ledger[i]["event_type"] != "REVISION_OBSERVATION" and ledger[i]["status"] == "CONFIRMED")
                next_state = symbol_candidate
                changed = True
            report["pending_review_events"].extend(copy.deepcopy(ledger[i]) for i in pending)
            report["stocks"].append(observation)
        except CatchupRequired as exc:
            report["stocks"].append({"symbol":symbol,"change_event":"DATA_ERROR","data_quality":"FAIL",
                "error_category":"CATCHUP_REQUIRED","missing_sessions":exc.missing_sessions,
                "error_message":str(exc),"previous_state_preserved":True,
                "recovery":"Supply verified consecutive archived snapshots; later-captured history is reconstructed, not Point-in-Time."})
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            report["stocks"].append({"symbol": symbol, "change_event": "DATA_ERROR", "data_quality": "FAIL", "error_message": str(exc),
                'error_category':'REOPEN_REQUIRED' if 'REOPEN_REQUIRED' in str(exc) else 'DATA_ERROR',
                "previous_state_preserved": symbol in previous["stocks"]})
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
    state._isolated_path(state_path)
    state.load(state_path)  # Fail before creating a lock directory or new baseline.
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
    parser.add_argument("--init-state",action="store_true",help="Explicitly initialize a fresh existing isolated directory")
    parser.add_argument('--archived-catchup',action='store_true',help='Manually apply one original archived session, never reconstructed history')
    parser.add_argument('--archive-attestation',help='Explicit operator rationale for trusting this original archive')
    args = parser.parse_args()
    if args.archived_catchup and (args.fetch or not args.input or not args.archive_attestation):
        parser.error('--archived-catchup requires --input and --archive-attestation, and forbids --fetch')
    try:
        state._isolated_path(args.state)  # Reject protected path before optional fetch.
        if args.init_state:
            if args.fetch:parser.error("Initialize offline before any explicit live collection")
            state.initialize(args.state)
        else:
            state.load(args.state)
        with state.lock(args.state):
            state.load(args.state)
            input_path = args.input or DEFAULT_INPUT
            if args.fetch:
                fetched = phase2.run(output_dir=args.output_dir)
                input_path = Path(fetched["price_evidence_file"])
            report = _run_unlocked(input_path, args.state, args.output_dir, args.significant_pp,
                'ARCHIVED_CATCHUP' if args.archived_catchup else "LIVE_FETCH" if args.fetch else "OFFLINE_SNAPSHOT")
        return int(report["failure_count"] > 0)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
