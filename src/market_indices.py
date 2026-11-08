"""Independent Market Indices v2 state and revision-safe technical observations."""
import argparse
import copy
import datetime as dt
import json
import math
from pathlib import Path

from src import index_data as data, indicators, signals, state

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "market_indices_trial"
DEFAULT_STATE = DIRECTORY / "state/indices_state.json"
MODEL = "indices-revision-market-v2"


def allowed_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(DIRECTORY.resolve()) or path.name != "indices_state.json":
        raise ValueError("INDEX_STATE_ISOLATION_ERROR: use market_indices_trial/**/indices_state.json")
    return path


def event_id(event):
    if event.get("symbol") not in data.SYMBOLS or event.get("category") != data.CATEGORY or event.get("event_model_version") != MODEL:
        raise ValueError("INDEX_EVENT_IDENTITY_ERROR")
    return state.fingerprint({k: event.get(k) for k in ("category", "symbol", "trading_date", "event_type", "threshold", "event_model_version", "rules_version")})


def register(document, symbol, date, kind, threshold, status, evidence):
    event = {"category": data.CATEGORY, "symbol": symbol, "trading_date": date, "event_type": kind,
             "threshold": threshold, "status": status, "event_model_version": MODEL, "rules_version": indicators.RULES_VERSION}
    key = event_id(event); event["event_id"] = key
    version = {"evidence_hash": state.fingerprint(evidence), "evidence": copy.deepcopy(evidence)}
    old = document["event_records"].get(key)
    if old:
        if any(v["evidence_hash"] == version["evidence_hash"] for v in old["evidence_versions"]):
            return key
        if old["status"] == "REJECTED":
            raise ValueError("REOPEN_REQUIRED: rejected index event has new evidence")
        old["evidence_versions"].append(version)
        if old["status"] == "CONFIRMED" and status == "PENDING_REVIEW" and kind == "REVISION_OBSERVATION":
            old["status"] = "PENDING_REVIEW"
            old["audit_trail"].append({"action": "RISK_ESCALATION", "to_status": "PENDING_REVIEW"})
        return key  # pending never auto-promotes
    event.update(evidence_versions=[version], audit_trail=[{"action": "CREATED", "to_status": status}])
    document["event_records"][key] = event
    return key


def load(path):
    path = allowed_path(path)
    if not path.is_file():
        raise ValueError("MISSING_EXISTING_INDEX_STATE: explicit initialization/recovery required")
    value = json.loads(path.read_text())
    if value.get("category") != data.CATEGORY or value.get("schema_version") != 2 or value.get("event_model_version") != MODEL or value.get("rules_version") != indicators.RULES_VERSION:
        raise ValueError("INDEX_STATE_SCHEMA_ERROR")
    if not isinstance(value.get("indices"), dict) or not set(value["indices"]).issubset(data.SYMBOLS):
        raise ValueError("INDEX_UNIVERSE_ERROR")
    for symbol, item in value["indices"].items():
        if item.get("symbol") != symbol:
            raise ValueError("INDEX_STATE_SYMBOL_ERROR")
        prices = item["history_prices"]
        if state.fingerprint(prices) != item["history_fingerprint"] or set(prices) != set(item["history_closes"]):
            raise ValueError("INDEX_HISTORY_INTEGRITY_ERROR")
        expected = indicators.calculate(sorted(prices.items()), item["trading_date"])
        for key in ("adjclose", "highest_adjclose", "drawdown", "rsi14", "sma50", "sma200"):
            if not math.isclose(item[key], expected[key], abs_tol=1e-8, rel_tol=1e-10):
                raise ValueError("INDEX_INDICATOR_INTEGRITY_ERROR")
        if (item["highest_date"] != expected["highest_date"] or item["watch_tier"] != signals.tier(expected["drawdown"])
                or not math.isfinite(item["deepening_anchor"]) or not set(item["confirmed_thresholds"]).issubset({10,20,30})
                or state.fingerprint({"closes": item["history_closes"], "identity": item["identity"]}) != item["comparison_fingerprint"]):
            raise ValueError("INDEX_COMPARISON_INTEGRITY_ERROR")
        # Revalidate identity, completed sessions, Close and Adj Close from state provenance.
        from src.index_data import validate
        raw = {"meta": item["identity"], "timestamp": [calendar_stamp(d) for d in sorted(prices)],
               "indicators": {"quote": [{"close": [item["history_closes"][d] for d in sorted(prices)]}],
                              "adjclose": [{"adjclose": [prices[d] for d in sorted(prices)]}]}}
        validate(symbol, {"chart": {"result": [raw]}}, dt.datetime.fromisoformat(item["as_of_utc"]))
    for key, event in value["event_records"].items():
        if key != event_id(event) or key != event["event_id"] or event["status"] not in ("CONFIRMED", "PENDING_REVIEW", "REJECTED"):
            raise ValueError("INDEX_LEDGER_INTEGRITY_ERROR")
        hashes = [v["evidence_hash"] for v in event["evidence_versions"]]
        if len(hashes) != len(set(hashes)) or not hashes or event["audit_trail"][-1]["to_status"] != event["status"]:
            raise ValueError("INDEX_LEDGER_EVIDENCE_ERROR")
        for version in event["evidence_versions"]:
            if state.fingerprint(version["evidence"]) != version["evidence_hash"]:
                raise ValueError("INDEX_LEDGER_EVIDENCE_ERROR")
    for symbol, item in value["indices"].items():
        for level in item["confirmed_thresholds"]:
            if not any(e["symbol"] == symbol and e["threshold"] == level and e["event_type"] == "THRESHOLD_CROSSING" and e["status"] == "CONFIRMED" for e in value["event_records"].values()):
                raise ValueError("INDEX_CONFIRMED_THRESHOLD_WITHOUT_EVENT")
    return value


def calendar_stamp(date):
    from market_calendar import session_bounds
    return int(session_bounds(dt.date.fromisoformat(date))[0].timestamp())


def initialize(path=DEFAULT_STATE):
    path = allowed_path(path)
    if not path.parent.is_dir():
        raise ValueError("INITIALIZATION_DIRECTORY_MISSING")
    with state.lock(path):
        if any(p.name not in (path.with_suffix(path.suffix+".lock").name, ".DS_Store") for p in path.parent.iterdir()):
            raise ValueError("INITIALIZATION_REFUSED: requires a new empty isolated directory")
        document = {"schema_version": 2, "category": data.CATEGORY, "event_model_version": MODEL,
                    "rules_version": indicators.RULES_VERSION, "commit_version": 1, "indices": {}, "event_records": {}, "review_history": []}
        state.durable_json(path.with_suffix(".initialized.json"), {"intent": "EXPLICIT_INDEX_INITIALIZATION", "path": str(path), "initial_fingerprint": state.fingerprint(document)})
        state.durable_json(path, document)
        load(path)


def evaluate(document, item):
    symbol, pairs, target = item["symbol"], [tuple(r) for r in item["pairs"]], item["target"]
    # Never trust a cached PASS alone; every invocation revalidates source evidence.
    raw = {"meta": item["identity"], "timestamp": [calendar_stamp(d) for d,p in pairs],
           "indicators": {"quote": [{"close": [item["closes"][d] for d,p in pairs]}], "adjclose": [{"adjclose": [p for d,p in pairs]}]}}
    data.validate(symbol, {"chart": {"result": [raw]}}, dt.datetime.fromisoformat(item["as_of_utc"]))
    metrics = indicators.calculate(pairs, target)
    old = document["indices"].get(symbol)
    from src.observations import missing_sessions
    if old and (target < old["trading_date"] or missing_sessions(old["trading_date"], target)):
        raise ValueError("CATCHUP_REQUIRED: no automatic reconstruction of missing original captures")
    prices = dict(pairs)
    from src import observations
    previous = copy.deepcopy(old)
    if previous:
        previous["identity_snapshot"] = previous["identity"]
        previous["threshold_state"] = {"baseline": previous["baseline_thresholds"], "confirmed": previous["confirmed_thresholds"], "pending_event_ids": []}
        previous["revision_review_event_ids"] = sorted(key for key,event in document["event_records"].items()
            if event["symbol"] == symbol and event["event_type"] == "REVISION_OBSERVATION" and event["status"] == "PENDING_REVIEW")
    model = observations.evaluate(symbol,pairs,item["closes"],item["identity"],previous,
                                  event_context=document["event_records"],identity_policy="INDEX")
    changes = model["revision_observation"]["raw_differences"]
    revision_id = None
    if changes:
        revision_id = register(document,symbol,target,"REVISION_OBSERVATION",None,
            "PENDING_REVIEW" if model["revision_observation"]["requires_review"] else "CONFIRMED",
            {"revision_observation":model["revision_observation"],"changes":changes,"snapshot_fingerprint":state.fingerprint(prices)})
    emitted = []
    for candidate in model["market_events"]:
        emitted.append(register(document,symbol,target,candidate["event_type"],candidate["threshold"],candidate["status"],
                                {**candidate["evidence"],"subtype":candidate["event_subtype"]}))
    confirmed = sorted(set(old["confirmed_thresholds"] if old else []) | {e["threshold"] for e in document["event_records"].values()
        if e["symbol"] == symbol and e["event_type"] == "THRESHOLD_CROSSING" and e["status"] == "CONFIRMED" and e["threshold"] is not None})
    baseline = model["baseline_observed_thresholds"]
    kind, anchor, comparable = model["change_event"], model["deepening_anchor"], model["market_observation"]["comparability_proven"]
    current = {**metrics, "symbol": symbol, "identity": item["identity"], "as_of_utc": item["as_of_utc"],
               "history_prices": prices, "history_closes": item["closes"], "history_fingerprint": state.fingerprint(prices),
               "comparison_fingerprint": state.fingerprint({"closes": item["closes"], "identity": item["identity"]}),
               "watch_tier": signals.tier(metrics["drawdown"]), "baseline_thresholds": baseline, "confirmed_thresholds": confirmed,
               "deepening_anchor": anchor, "change_event": kind, "market_event_ids": emitted,
               "revision_observation": {"count": len(changes), "event_id": revision_id, "requires_review": model["revision_observation"]["requires_review"]},
               "comparability_proven": comparable, "revision_policy": "Same-basis attribution; disputed candidates retained pending; INDEX Close never determines events",
               "technical_observation_only": True}
    current.update({key:model[key] for key in ("daily_drawdown_change_pp","daily_new_deepening","cumulative_anchor_deepening_pp",
                                               "raw_market_candidate_type","event_status","candidate_confirmed","daily_drawdown_change_basis","stored_previous_drawdown_change_pp")})
    current["latest_basis_daily_drawdown_change_pp"] = model.get("latest_basis_daily_drawdown_change_pp")
    current["market_observation"] = model["market_observation"]
    current["revision_observation"].update({key:value for key,value in model["revision_observation"].items() if key != "event_id"})
    document["indices"][symbol] = current
    return {k:v for k,v in current.items() if k not in ("history_prices", "history_closes")}


def run(items, path=DEFAULT_STATE, output=DIRECTORY/"reports"):
    if not Path(output).resolve().is_relative_to(DIRECTORY.resolve()):
        raise ValueError("INDEX_REPORT_ISOLATION_ERROR")
    path = allowed_path(path); load(path)
    with state.lock(path):
        original = load(path); candidate = copy.deepcopy(original); rows = []
        for symbol in data.SYMBOLS:
            single = copy.deepcopy(candidate)
            try:
                row = evaluate(single, items[symbol])
                # Identical replay must preserve source, event evidence and state bytes.
                if (original["indices"].get(symbol) and original["indices"][symbol]["history_prices"] == single["indices"][symbol]["history_prices"]
                        and original["indices"][symbol]["history_closes"] == single["indices"][symbol]["history_closes"]
                        and original["event_records"] == single["event_records"]):
                    row["change_event"] = "NO_CHANGE"
                else:
                    candidate = single
                rows.append(row)
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                rows.append({"symbol": symbol, "change_event": "DATA_ERROR", "error": str(exc), "previous_state_preserved": True})
        changed = candidate != original
        if changed:
            candidate["commit_version"] = original["commit_version"]+1
            check = path.with_suffix(".candidate.json")
            try:
                state.durable_json(check, candidate)
                # Candidate validation uses the same restricted basename in a separate temp directory.
                import tempfile
                with tempfile.TemporaryDirectory(dir=path.parent) as directory:
                    temp = Path(directory)/"indices_state.json"; state.durable_json(temp,candidate); load(temp)
                state.durable_json(path.with_name("indices_state.backup.json"), original)
                check.replace(path); state.sync_directory(path.parent)
            finally:
                if check.exists(): check.unlink()
        report = {"category": data.CATEGORY, "event_model_version": MODEL, "rules_version": indicators.RULES_VERSION,
                  "state_updated": changed, "commit_version": candidate["commit_version"], "indices": rows,
                  "success_count": sum(r["change_event"] != "DATA_ERROR" for r in rows),
                  "pending_event_ids": [k for k,e in candidate["event_records"].items() if e["status"] == "PENDING_REVIEW"]}
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        import time
        name=output/f"indices_{time.time_ns()}.json"; state.durable_json(name,report)
        lines=["# Market Indices — 技术观察", "", "| Index | 日期 | Adj Close | 回撤 | RSI14 | SMA50 | SMA200 | WATCH | 事件 |", "|---|---|---|---|---|---|---|---|---|"]
        lines += ["| "+" | ".join(str(r.get(k,"N/A")) for k in ("symbol","trading_date","adjclose","drawdown","rsi14","sma50","sma200","watch_tier","change_event"))+" |" for r in rows]
        lines += ["", "| Index | Daily drawdown change (pp) | New deepening today | Cumulative anchor depth (pp) | Raw candidate | Status | Confirmed |",
                  "|---|---|---|---|---|---|---|"]
        lines += ["| "+" | ".join(str(r.get(k,"N/A")) for k in ('symbol','daily_drawdown_change_pp','daily_new_deepening','cumulative_anchor_deepening_pp','raw_market_candidate_type','event_status','candidate_confirmed'))+" |" for r in rows]
        lines += ["", "仅为指数技术观察；Yahoo单一数据源；历史修订按可比性归因，不直接构成交易信号。"]
        name.with_suffix('.md').write_text('\n'.join(lines)+'\n')
        report["report_file"]=str(name)
        return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--init-state',action='store_true');parser.add_argument('--state',type=Path,default=DEFAULT_STATE)
    parser.add_argument('--input',type=Path);args=parser.parse_args()
    if args.init_state: initialize(args.state)
    elif args.input: print(json.dumps(run(json.loads(args.input.read_text()),args.state),ensure_ascii=False))
    else: parser.error('Select --init-state or --input; no implicit collection/initialization')
