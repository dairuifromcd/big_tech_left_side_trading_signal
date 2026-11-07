"""Fail-closed JSON state with overlapping-date revision evidence and atomic save."""
import hashlib
import json
import math
import datetime as dt
import contextlib
import fcntl
import os
import copy
from pathlib import Path
from test_yahoo_nine import atomic_json
from src.indicators import RULES_VERSION, calculate
from src.signals import tier

SYMBOLS = ("NVDA", "AAPL", "GOOGL", "MSFT", "AMZN", "SPCX", "META", "AVGO", "TSLA")
EVENT_MODEL_VERSION = "revision-market-v2"
EVENT_STATUSES = frozenset(("PENDING_REVIEW", "CONFIRMED", "REJECTED"))
EVENT_ID_FIELDS = ("symbol", "trading_date", "event_type", "threshold", "rules_version", "event_model_version")


class StateError(ValueError):
    pass


def fingerprint(prices):
    return hashlib.sha256(json.dumps(prices, sort_keys=True, allow_nan=False).encode()).hexdigest()


def load(path, *, allow_missing=False):
    path = Path(path)
    if not path.exists():
        if allow_missing:
            return {"schema_version": 1, "rules_version": RULES_VERSION, "stocks": {}}
        directory = path.with_name(path.name + ".backups")
        backups=list_backups(path) if directory.is_dir() else []
        valid=[item['path'] for item in backups if item['valid']]
        error=StateError(f"MISSING_EXISTING_STATE: {path}; validated backups={valid}; backup directory={directory}; use explicit recover; never implicit initialization")
        error.backups=backups
        raise error
    try:
        value = json.loads(path.read_text())
        if value["schema_version"] not in (1, 2) or value["rules_version"] != RULES_VERSION or not isinstance(value["stocks"], dict):
            raise ValueError("unsupported state schema or calculation rules")
        for symbol, stock in value["stocks"].items():
            if symbol not in SYMBOLS or stock["source"] != "YAHOO_CHART_ADJCLOSE":
                raise ValueError("unknown symbol/source")
            prices = stock["history_prices"]
            if not isinstance(prices, dict) or not prices or fingerprint(prices) != stock["history_fingerprint"]:
                raise ValueError("missing or invalid history fingerprint")
            for price in prices.values():
                if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                    raise ValueError("invalid history price")
            if stock["trading_date"] != max(prices) or stock["adjclose"] != prices[stock["trading_date"]]:
                raise ValueError("state date/price inconsistent")
            if stock["watch_tier"] != tier(stock["drawdown"]) or not set(stock["triggered_thresholds"]).issubset({10, 20, 30}):
                raise ValueError("invalid tier/threshold state")
            for key in ("highest_adjclose", "highest_date", "rsi14", "sma50", "sma200", "data_quality", "last_new_trigger_date", "deepening_anchor", "previous_watch_tier"):
                stock[key]
            recomputed = calculate(sorted(prices.items()), stock["trading_date"], allow_short=symbol == "SPCX")
            for key in ("drawdown", "highest_adjclose", "adjclose", "rsi14", "sma50", "sma200"):
                expected, actual = recomputed[key], stock[key]
                if expected is None:
                    if actual is not None:
                        raise ValueError("invalid stored indicator availability")
                elif isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual) or not math.isclose(actual, expected, abs_tol=1e-8, rel_tol=1e-10):
                    raise ValueError("stored indicators inconsistent with history")
            if stock["highest_date"] != recomputed["highest_date"] or not math.isfinite(stock["deepening_anchor"]):
                raise ValueError("invalid stored high/anchor")
            if stock["last_new_trigger_date"] is not None:
                dt.date.fromisoformat(stock["last_new_trigger_date"])
        if value["schema_version"] == 2:
            validate_v2(value)
        return value
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise StateError(f"STATE_READ_ERROR: refusing to reset {path}: {exc}") from exc


def _levels(values):
    if not isinstance(values, list) or values != sorted(set(values)) or not set(values).issubset({10, 20, 30}):
        raise StateError("STATE_SCHEMA_ERROR: invalid threshold list")
    return values


def _observed(drawdown):
    return [n for n in (10, 20, 30) if drawdown * 100 <= -n + 1e-10]


def stable_id(event):
    """Semantic identity survives status promotion and evidence resampling."""
    semantic = {key: event.get(key) for key in EVENT_ID_FIELDS}
    semantic["rules_version"] = semantic["rules_version"] or RULES_VERSION
    semantic["event_model_version"] = semantic["event_model_version"] or EVENT_MODEL_VERSION
    if semantic["symbol"] not in SYMBOLS or not isinstance(semantic["event_type"], str) or not semantic["event_type"]:
        raise StateError("EVENT_SCHEMA_ERROR: invalid symbol or event type")
    dt.date.fromisoformat(semantic["trading_date"])
    if semantic["threshold"] not in (None, 10, 20, 30):
        raise StateError("EVENT_SCHEMA_ERROR: invalid threshold")
    if semantic["rules_version"] != RULES_VERSION or semantic["event_model_version"] != EVENT_MODEL_VERSION:
        raise StateError("EVENT_SCHEMA_ERROR: unsupported event model or indicator rules")
    return fingerprint(semantic)


def validate_v2(value):
    """Validate ledger integrity without deriving confirmation from current tier."""
    if value.get("event_model_version") != EVENT_MODEL_VERSION or not isinstance(value.get("event_records"), dict):
        raise StateError("STATE_SCHEMA_ERROR: missing v2 event model/ledger")
    if not isinstance(value.get("legacy_event_records", {}), dict) or not isinstance(value.get("review_history", []), list):
        raise StateError("STATE_SCHEMA_ERROR: invalid legacy ledger or review history")
    for event_id, event in value["event_records"].items():
        if not isinstance(event, dict) or event_id != stable_id(event) or event.get("event_id") != event_id:
            raise StateError("EVENT_INTEGRITY_ERROR: semantic event ID mismatch")
        if event.get("status") not in EVENT_STATUSES:
            raise StateError("EVENT_SCHEMA_ERROR: invalid status; delivery is not modeled")
        versions = event.get("evidence_versions")
        if not isinstance(versions, list) or not versions or not isinstance(event.get("audit_trail"), list) or not event["audit_trail"]:
            raise StateError("EVENT_INTEGRITY_ERROR: evidence/audit missing")
        hashes = set()
        for version in versions:
            if version.get("evidence_hash") != fingerprint(version.get("evidence")) or version["evidence_hash"] in hashes:
                raise StateError("EVENT_INTEGRITY_ERROR: evidence version mismatch/duplicate")
            hashes.add(version["evidence_hash"])
        if event["audit_trail"][-1].get("to_status") != event["status"]:
            raise StateError("EVENT_INTEGRITY_ERROR: audit/status mismatch")
    for symbol, stock in value["stocks"].items():
        confirmed = _levels(stock.get("confirmed_thresholds"))
        threshold_state = stock.get("threshold_state")
        if not isinstance(threshold_state, dict) or _levels(threshold_state.get("confirmed")) != confirmed:
            raise StateError("STATE_SCHEMA_ERROR: confirmed threshold aliases disagree")
        if stock["triggered_thresholds"] != confirmed:
            raise StateError("STATE_SCHEMA_ERROR: v2 triggered thresholds must mean confirmed only")
        if _levels(threshold_state.get("observed")) != _observed(stock["drawdown"]):
            raise StateError("STATE_SCHEMA_ERROR: observed thresholds inconsistent with drawdown")
        _levels(threshold_state.get("baseline"))
        if stock.get("history_closes") is not None:
            closes = stock["history_closes"]
            if (not isinstance(closes, dict) or set(closes) != set(stock["history_prices"])
                    or any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0 for p in closes.values())):
                raise StateError("COMPARISON_EVIDENCE_ERROR: invalid Close history")
            if stock.get("comparison_evidence_fingerprint") != fingerprint({"closes": closes, "identity": stock.get("identity_snapshot")}):
                raise StateError("COMPARISON_EVIDENCE_ERROR: Close/identity fingerprint mismatch")
        pending = threshold_state.get("pending_event_ids")
        if not isinstance(pending, list) or len(pending) != len(set(pending)):
            raise StateError("STATE_SCHEMA_ERROR: invalid pending event references")
        for event_id in pending:
            event = value["event_records"].get(event_id)
            if event is None or event["symbol"] != symbol or event["status"] != "PENDING_REVIEW":
                raise StateError("STATE_SCHEMA_ERROR: pending event reference is not pending")
        if "revision_review_event_ids" in stock:
            actual_revision_pending = sorted(i for i,e in value["event_records"].items()
                if e["symbol"] == symbol and e["event_type"] == "REVISION_OBSERVATION" and e["status"] == "PENDING_REVIEW")
            if sorted(stock["revision_review_event_ids"]) != actual_revision_pending:
                raise StateError("STATE_SCHEMA_ERROR: unresolved revision review references disagree with ledger")
        for threshold in confirmed:
            if not any(e["symbol"] == symbol and e["threshold"] == threshold and e["status"] == "CONFIRMED"
                       and e["event_type"] in ("THRESHOLD_CROSSING", "LEGACY_THRESHOLD_REVIEW")
                       for e in value["event_records"].values()):
                raise StateError("STATE_SCHEMA_ERROR: confirmed threshold lacks confirmed market/review evidence")


def register_event(document, event):
    """Mutate only an in-memory candidate; never auto-promote an existing event."""
    if document.get("schema_version") != 2:
        raise StateError("EVENT_SCHEMA_ERROR: migrate state before registering v2 events")
    event = copy.deepcopy(event)
    event.setdefault("rules_version", RULES_VERSION)
    event.setdefault("event_model_version", EVENT_MODEL_VERSION)
    event.setdefault("threshold", None)
    event_id = stable_id(event)
    if event.get("event_id", event_id) != event_id:
        raise StateError("EVENT_INTEGRITY_ERROR: supplied ID does not match semantics")
    status = event.get("status", "PENDING_REVIEW")
    if status not in EVENT_STATUSES:
        raise StateError("EVENT_SCHEMA_ERROR: invalid status")
    excluded = set(EVENT_ID_FIELDS) | {"event_id", "status", "reason", "audit_trail", "evidence_versions"}
    evidence = event.get("evidence", {k: v for k, v in event.items() if k not in excluded})
    version = {"evidence_hash": fingerprint(evidence), "evidence": copy.deepcopy(evidence)}
    ledger = document.setdefault("event_records", {})
    if event_id in ledger:
        existing = ledger[event_id]
        unseen = not any(v["evidence_hash"] == version["evidence_hash"] for v in existing["evidence_versions"])
        if unseen and event["event_type"] == "REVISION_OBSERVATION" and existing["status"] == "REJECTED":
            raise StateError("REOPEN_REQUIRED: new evidence for rejected revision; existing state protected")
        if unseen and event["event_type"] == "REVISION_OBSERVATION" and existing["status"] == "CONFIRMED" and status == "PENDING_REVIEW":
            revision = evidence.get("revision_observation", evidence) if isinstance(evidence, dict) else {}
            if revision.get("requires_review") is not True:
                raise StateError("RISK_EVIDENCE_REQUIRED: explicit requires_review=true needed")
        if unseen:
            existing["evidence_versions"].append(version)
        if (unseen and event["event_type"] == "REVISION_OBSERVATION"
                and existing["status"] == "CONFIRMED" and status == "PENDING_REVIEW"):
            existing["status"] = "PENDING_REVIEW"
            existing["audit_trail"].append({"from_status":"CONFIRMED","to_status":"PENDING_REVIEW",
                "action":"RISK_ESCALATION","reason":event.get("reason", "New revision evidence requires review"),
                "evidence_hash":version["evidence_hash"],"at_utc":dt.datetime.now(dt.timezone.utc).isoformat()})
            document.setdefault('review_history',[]).append({'event_id':event_id,**copy.deepcopy(existing['audit_trail'][-1])})
            _mark_dependency_risk(document, existing)
        _sync_review_refs(document, event["symbol"])
        # Review is sticky. Lighter evidence never clears risk or confirms a
        # market candidate; only explicit review_event can resolve it.
        return event_id, False
    stored = {k: v for k, v in event.items() if k not in ("audit_trail", "evidence_versions", "evidence")}
    stored.update({"event_id": event_id, "status": status, "evidence_versions": [version],
                   "audit_trail": [{"from_status": None, "to_status": status, "action": "REGISTER",
                                    "reason": event.get("reason", "Initial evidence registration"),
                                    "at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}]})
    ledger[event_id] = stored
    if event["event_type"] == "REVISION_OBSERVATION" and status == "PENDING_REVIEW":
        _mark_dependency_risk(document, stored)
    _sync_review_refs(document, event["symbol"])
    return event_id, True


def _sync_review_refs(document, symbol):
    stock = document.get("stocks", {}).get(symbol)
    if stock is None or "threshold_state" not in stock:
        return
    pending = {i:e for i,e in document["event_records"].items() if e["symbol"] == symbol and e["status"] == "PENDING_REVIEW"}
    stock["threshold_state"]["pending_event_ids"] = sorted(pending)
    stock["revision_review_event_ids"] = sorted(i for i,e in pending.items() if e["event_type"] == "REVISION_OBSERVATION")


def _mark_dependency_risk(document, revision):
    """Flag existing confirmations without silently revoking their status."""
    revision_id=revision["event_id"]
    for event in document["event_records"].values():
        if (event["symbol"] == revision["symbol"] and event["trading_date"] >= revision["trading_date"]
                and event["event_type"] != "REVISION_OBSERVATION" and event["status"] == "CONFIRMED"):
            dependencies=event.setdefault("dependency_review_event_ids", [])
            if revision_id not in dependencies:
                dependencies.append(revision_id);dependencies.sort()
                event["audit_trail"].append({"from_status":"CONFIRMED","to_status":"CONFIRMED",
                    "action":"DEPENDENCY_RISK","revision_event_id":revision_id,
                    "reason":"Revision risk requires review; prior confirmation retained, not revoked",
                    "at_utc":dt.datetime.now(dt.timezone.utc).isoformat()})


def migrate(value):
    """Pure v1->v2 migration; ambiguous legacy 'touched' levels stay unconfirmed."""
    value = copy.deepcopy(value)
    if value.get("schema_version") == 2:
        validate_v2(value)
        return value, {"changed": False, "from_schema": 2, "to_schema": 2, "ambiguous_thresholds": []}
    if value.get("schema_version") != 1 or value.get("rules_version") != RULES_VERSION:
        raise StateError("MIGRATION_ERROR: unsupported state schema/rules")
    legacy = copy.deepcopy(value.get("event_records", {}))
    if not isinstance(legacy, dict):
        raise StateError("MIGRATION_ERROR: legacy event ledger malformed")
    value.update({"schema_version": 2, "event_model_version": EVENT_MODEL_VERSION,
                  "legacy_event_records": legacy, "event_records": {}, "review_history": []})
    ambiguities, confirmations = [], []
    for symbol, stock in value["stocks"].items():
        old_levels = sorted(set(stock["triggered_thresholds"]))
        stock["legacy_triggered_thresholds"] = old_levels
        stock["confirmed_thresholds"] = []
        stock["triggered_thresholds"] = []
        stock["threshold_state"] = {"observed": _observed(stock["drawdown"]),
                                    "baseline": _observed(stock["drawdown"]),
                                    "confirmed": [], "pending_event_ids": []}
        trustworthy = {}
        for old_id, old_event in legacy.items():
            if not isinstance(old_event, dict) or old_event.get("symbol") != symbol:
                continue
            semantic = {k: v for k, v in old_event.items() if k != "data_quality"}
            levels = old_event.get("crossed_thresholds_this_run")
            date = old_event.get("trading_date")
            valid_date = False
            try:
                valid_date = isinstance(date, str) and dt.date.fromisoformat(date).isoformat() == date and date <= stock["trading_date"]
            except (TypeError, ValueError):
                pass
            if (old_id == fingerprint(semantic) and old_event.get("change_event") in ("NEW_THRESHOLD", "REENTRY")
                    and old_event.get("rules_version") == RULES_VERSION and old_event.get("data_quality") == "PASS"
                    and valid_date and isinstance(levels, list) and levels and set(levels).issubset({10, 20, 30})):
                # A revision recorded on the same symbol/date makes attribution
                # ambiguous in legacy state, even if another record says crossing.
                conflict = any(e.get("symbol") == symbol and e.get("trading_date") == date
                               and e.get("change_event") == "HISTORICAL_REVISION"
                               for e in legacy.values() if isinstance(e, dict))
                if not conflict:
                    for threshold in levels:
                        trustworthy.setdefault(threshold, (date, old_id, old_event))
        for threshold, (date, old_id, old_event) in trustworthy.items():
            event_id, _ = register_event(value, {"symbol": symbol, "trading_date": date,
                "event_type": "THRESHOLD_CROSSING", "threshold": threshold, "status": "CONFIRMED",
                "market_kind": old_event["change_event"], "reason": "Verified legacy market-event semantic hash and quality",
                "evidence": {"legacy_event_id": old_id, "legacy_event": old_event, "migration": True}})
            stock["confirmed_thresholds"].append(threshold)
            confirmations.append({"symbol": symbol, "threshold": threshold, "event_id": event_id})
        stock["confirmed_thresholds"].sort()
        stock["triggered_thresholds"] = list(stock["confirmed_thresholds"])
        stock["threshold_state"]["confirmed"] = list(stock["confirmed_thresholds"])
        stock["migration_ambiguities"] = []
        for threshold in sorted(set(old_levels) - set(stock["confirmed_thresholds"])):
            ambiguity = {"symbol": symbol, "threshold": threshold,
                         "reason": "Legacy touched level lacks a verified, non-revision market-event record"}
            event_id, _ = register_event(value, {"symbol": symbol, "trading_date": stock["trading_date"],
                "event_type": "LEGACY_THRESHOLD_REVIEW", "threshold": threshold, "status": "PENDING_REVIEW",
                "reason": ambiguity["reason"], "evidence": {"legacy_triggered_thresholds": old_levels, "migration": True}})
            if event_id not in stock["threshold_state"]["pending_event_ids"]:
                stock["threshold_state"]["pending_event_ids"].append(event_id)
            stock["migration_ambiguities"].append({**ambiguity, "event_id": event_id})
            ambiguities.append({**ambiguity, "event_id": event_id})
    report = {"changed": True, "from_schema": 1, "to_schema": 2, "ambiguous_thresholds": ambiguities,
              "verified_legacy_confirmations": confirmations, "alert_delivery": "NONE"}
    value["migration_report"] = copy.deepcopy(report)
    validate_v2(value)
    return value, report


def _isolated_path(path):
    path = Path(path)
    formal = Path(__file__).resolve().parents[1] / "state/monitor_state.json"
    if path.resolve() == formal.resolve():
        raise StateError("ISOLATION_ERROR: formal Phase 3 state is read-only for migration/review")
    return path


def migrate_path(path):
    path = _isolated_path(path)
    if not path.exists():
        raise StateError("MIGRATION_ERROR: source state does not exist")
    with lock(path):
        value, report = migrate(load(path))
        if report["changed"]:
            save(path, value)
    return report


def review_event(path, event_id, decision, reason):
    path = _isolated_path(path)
    load(path)  # A typo must not create a new lock directory/checkpoint.
    if not isinstance(reason, str) or not reason.strip():
        raise StateError("REVIEW_ERROR: an explicit rationale is required")
    aliases = {"CONFIRM": "CONFIRMED", "CONFIRMED": "CONFIRMED", "REJECT": "REJECTED",
               "REJECTED": "REJECTED", "KEEP": "PENDING_REVIEW", "PENDING_REVIEW": "PENDING_REVIEW"}
    if decision not in aliases:
        raise StateError("REVIEW_ERROR: choose CONFIRM, REJECT or KEEP")
    target = aliases[decision]
    with lock(path):
        value = load(path)
        if value.get("schema_version") != 2 or event_id not in value["event_records"]:
            raise StateError("REVIEW_ERROR: unknown v2 event")
        event = value["event_records"][event_id]
        previous = event["status"]
        revision_rollback = event["event_type"] == "REVISION_OBSERVATION" and target == "REJECTED"
        if previous != "PENDING_REVIEW":
            if previous == target:
                return {"event_id": event_id, "status": previous, "changed": False, "delivery": "NONE"}
            if not (revision_rollback and previous == "CONFIRMED"):
                raise StateError("REVIEW_ERROR: terminal event cannot be silently reclassified")
        rollback_stock = None
        snapshot = None
        if revision_rollback:
            for version in reversed(event["evidence_versions"]):
                evidence = version["evidence"]
                if isinstance(evidence, dict) and evidence.get("previous_valid_stock") is not None and evidence.get("snapshot_fingerprint"):
                    rollback_stock = copy.deepcopy(evidence["previous_valid_stock"])
                    snapshot = evidence["snapshot_fingerprint"]
                    break
            if not isinstance(rollback_stock, dict) or not isinstance(rollback_stock.get("threshold_state"), dict):
                raise StateError("REVIEW_ERROR: revision rejection requires a verified prior v2 stock checkpoint")
            if fingerprint(rollback_stock.get("history_prices")) != rollback_stock.get("history_fingerprint"):
                raise StateError("REVIEW_ERROR: prior stock checkpoint fingerprint mismatch")
            if value["stocks"].get(event["symbol"], {}).get("history_fingerprint") != snapshot:
                raise StateError("REVIEW_ERROR: state has advanced beyond rejected snapshot; select an explicit recovery checkpoint")
        audit = {"event_id": event_id, "from_status": previous, "to_status": target,
                 "action": "MANUAL_REVIEW", "reason": reason.strip()}
        if event["audit_trail"] and all(event["audit_trail"][-1].get(k) == v for k, v in audit.items()):
            return {"event_id": event_id, "status": previous, "changed": False, "delivery": "NONE"}
        audit["at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        event["status"] = target
        event["audit_trail"].append(copy.deepcopy(audit))
        value["review_history"].append(copy.deepcopy(audit))
        related_rejected = []
        if revision_rollback:
            for related_id, related in value["event_records"].items():
                if related_id == event_id or related["symbol"] != event["symbol"] or related["trading_date"] != event["trading_date"]:
                    continue
                matched = any(isinstance(v["evidence"], dict) and v["evidence"].get("snapshot_fingerprint") == snapshot
                              for v in related["evidence_versions"])
                if matched and related["status"] != "REJECTED":
                    related_audit = {"event_id": related_id, "from_status": related["status"], "to_status": "REJECTED",
                                     "action": "MANUAL_REVISION_ROLLBACK", "reason": reason.strip(),
                                     "revision_event_id": event_id, "at_utc": audit["at_utc"]}
                    related["status"] = "REJECTED"
                    related["audit_trail"].append(copy.deepcopy(related_audit))
                    value["review_history"].append(copy.deepcopy(related_audit))
                    related_rejected.append(related_id)
            current = value["stocks"].get(event["symbol"], {})
            rejected = set(current.get("rejected_snapshot_fingerprints", [])) | set(rollback_stock.get("rejected_snapshot_fingerprints", [])) | {snapshot}
            rollback_stock["rejected_snapshot_fingerprints"] = sorted(rejected)
            rollback_stock["threshold_state"]["pending_event_ids"] = [i for i in rollback_stock["threshold_state"]["pending_event_ids"]
                if i in value["event_records"] and value["event_records"][i]["status"] == "PENDING_REVIEW"]
            rollback_stock["last_rejected_revision_event_id"] = event_id
            value["stocks"][event["symbol"]] = rollback_stock
        stock = value["stocks"].get(event["symbol"])
        if stock is not None:
            threshold_state = stock["threshold_state"]
            if target != "PENDING_REVIEW":
                threshold_state["pending_event_ids"] = [i for i in threshold_state["pending_event_ids"] if i != event_id]
            if target == "CONFIRMED" and event["event_type"] in ("THRESHOLD_CROSSING", "LEGACY_THRESHOLD_REVIEW") and event["threshold"] is not None:
                stock["confirmed_thresholds"] = sorted(set(stock["confirmed_thresholds"]) | {event["threshold"]})
                stock["triggered_thresholds"] = list(stock["confirmed_thresholds"])
                threshold_state["confirmed"] = list(stock["confirmed_thresholds"])
            stock["revision_review_event_ids"] = sorted(i for i,e in value["event_records"].items()
                if e["symbol"] == event["symbol"] and e["event_type"] == "REVISION_OBSERVATION" and e["status"] == "PENDING_REVIEW")
        if event['event_type']=='REVISION_OBSERVATION' and target=='CONFIRMED':
            for dependent in value['event_records'].values():
                refs=dependent.get('dependency_review_event_ids',[])
                if event_id in refs:
                    refs.remove(event_id)
                    dependent['audit_trail'].append({'from_status':dependent['status'],'to_status':dependent['status'],
                        'action':'DEPENDENCY_REVIEW_RESOLVED','revision_event_id':event_id,'reason':reason.strip(),'at_utc':audit['at_utc']})
        save(path, value)
    return {"event_id": event_id, "status": target, "changed": True, "delivery": "NONE",
            "price_checkpoint_restored": revision_rollback, "related_rejected_event_ids": related_rejected}


def revisions(previous, prices):
    if previous is None:
        return []
    old = previous["history_prices"]
    if not old.keys() & prices.keys():
        raise StateError("NO_OVERLAPPING_HISTORY: cannot establish trustworthy continuity")
    return [{"date": date, "previous": old[date], "current": prices[date]}
            for date in sorted(old.keys() & prices.keys())
            if not math.isclose(old[date], prices[date], rel_tol=1e-10, abs_tol=1e-8)]


@contextlib.contextmanager
def lock(path):
    """Stable inode lock; never unlink it. Kernel releases on exit or crash."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise StateError("STATE_LOCKED: another process holds this state") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def sync_directory(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_json(path, value):
    atomic_json(path, value)
    sync_directory(Path(path).parent)


BACKUP_LIMIT = 3


def save(path, value, *, _initializing=False):
    """Caller holds lock. Validate candidate, back up valid old state, commit once."""
    path = Path(path)
    if not path.parent.is_dir():
        raise StateError("STATE_DIRECTORY_MISSING: create/select the directory explicitly")
    candidate = path.with_suffix(".candidate.json")
    try:
        old = load(path, allow_missing=_initializing)
        value = dict(value, commit_version=old.get("commit_version", 0) + 1)
        durable_json(candidate, value)
        load(candidate)
        if path.exists():
            directory = path.with_name(path.name + ".backups")
            directory.mkdir(exist_ok=True)
            version = old.get("commit_version", 0)
            digest = fingerprint(old)
            backup = directory / f"{version:08d}_{digest}.json"
            durable_json(backup, {"backup_version": version, "state_hash": digest, "state": old})
            for extra in sorted(directory.glob("*.json"), reverse=True)[BACKUP_LIMIT:]:
                extra.unlink()
            sync_directory(directory)
        if not _initializing and not path.exists():
            raise StateError("MISSING_EXISTING_STATE: disappeared before commit; validated backup retained")
        os.replace(candidate, path)
        sync_directory(path.parent)
    finally:
        if candidate.exists():
            candidate.unlink()


def initialize(path, value=None):
    """Explicit new checkpoint intent, never inferred by monitoring or saving."""
    path = _isolated_path(path)
    if not path.parent.is_dir():
        raise StateError("INITIALIZATION_DIRECTORY_MISSING: select/create a new isolated directory explicitly")
    with lock(path):
        marker=path.with_name(path.name+'.initialized.json')
        backups=path.with_name(path.name+'.backups')
        remnants=[path.with_suffix('.candidate.json'),path.with_suffix('.recovery.json')]
        if path.exists() or marker.exists() or backups.exists() or path.with_name(path.name+'.recovery_audit').exists() or any(p.exists() for p in remnants):
            raise StateError("INITIALIZATION_REFUSED: existing state, initialization receipt or backup requires explicit recovery")
        allowed={path.with_suffix(path.suffix+'.lock').name,'.DS_Store'}
        if any(entry.name not in allowed for entry in path.parent.iterdir()):
            raise StateError("INITIALIZATION_REFUSED: choose a fresh isolated directory, not an existing project/run directory")
        candidate=copy.deepcopy(value) if value is not None else migrate({"schema_version":1,"rules_version":RULES_VERSION,"stocks":{}})[0]
        # Validate before creating the permanent initialization receipt.
        validation=path.with_suffix('.init-validation.json')
        try:
            durable_json(validation,candidate);load(validation)
        finally:
            if validation.exists():validation.unlink()
        durable_json(marker,{'intent':'EXPLICIT_INITIALIZATION','path':str(path.resolve()),
                             'initial_content_hash':fingerprint(candidate),'at_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
        save(path,candidate,_initializing=True)
    return {'initialized':True,'state':str(path),'intent':'EXPLICIT_INITIALIZATION'}


def list_backups(path):
    """Read-only inventory. Validate envelope and complete state in a temp file."""
    import tempfile
    directory=Path(path).with_name(Path(path).name+'.backups')
    result=[]
    for backup in sorted(directory.glob('*.json')):
        item={'path':str(backup),'valid':False}
        try:
            envelope=json.loads(backup.read_text());value=envelope['state']
            if envelope['state_hash']!=fingerprint(value) or envelope['backup_version']!=value.get('commit_version',0):
                raise StateError('BACKUP_INTEGRITY_ERROR')
            with tempfile.TemporaryDirectory() as temp:
                check=Path(temp)/'state.json';atomic_json(check,value);load(check)
            item.update(valid=True,version=envelope['backup_version'],state_hash=envelope['state_hash'])
        except (ValueError,OSError,KeyError,TypeError) as exc:item['error']=str(exc)
        result.append(item)
    return result


def recover(path, backup):
    """Explicit selected backup only; never silently choose or reset state."""
    path, backup = _isolated_path(path), Path(backup)
    envelope = json.loads(backup.read_text())
    value = envelope["state"]
    if envelope["state_hash"] != fingerprint(value) or envelope["backup_version"] != value.get("commit_version", 0):
        raise StateError("BACKUP_INTEGRITY_ERROR")
    with lock(path):
        before_hash=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        candidate = path.with_suffix(".recovery.json")
        try:
            durable_json(candidate, value)
            load(candidate)
            if path.exists():
                # Preserve damaged bytes for diagnosis before explicit recovery.
                raw = path.read_bytes()
                quarantine = path.with_name(path.name + ".damaged_" + hashlib.sha256(raw).hexdigest())
                if not quarantine.exists():
                    with quarantine.open("wb") as f:
                        f.write(raw); f.flush(); os.fsync(f.fileno())
            os.replace(candidate, path)
            sync_directory(path.parent)
            audit_dir=path.with_name(path.name+'.recovery_audit');audit_dir.mkdir(exist_ok=True)
            receipt=audit_dir/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
            durable_json(receipt,{'action':'EXPLICIT_BACKUP_RECOVERY','backup':str(backup.resolve()),'state_hash_before':before_hash,
                                 'state_hash_after':hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'warning':'Backup rollback can restore older event decisions; reconcile stable IDs before future delivery.'})
        finally:
            if candidate.exists():
                candidate.unlink()
    return {"recovered": True, "backup": str(backup), "state_hash": fingerprint(value)}
