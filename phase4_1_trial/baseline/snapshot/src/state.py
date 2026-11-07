"""Fail-closed JSON state with overlapping-date revision evidence and atomic save."""
import hashlib
import json
import math
import datetime as dt
import contextlib
import fcntl
import os
from pathlib import Path
from test_yahoo_nine import atomic_json
from src.indicators import RULES_VERSION, calculate
from src.signals import tier

SYMBOLS = ("NVDA", "AAPL", "GOOGL", "MSFT", "AMZN", "SPCX", "META", "AVGO", "TSLA")


class StateError(ValueError):
    pass


def fingerprint(prices):
    return hashlib.sha256(json.dumps(prices, sort_keys=True, allow_nan=False).encode()).hexdigest()


def load(path):
    path = Path(path)
    if not path.exists():
        return {"schema_version": 1, "rules_version": RULES_VERSION, "stocks": {}}
    try:
        value = json.loads(path.read_text())
        if value["schema_version"] != 1 or value["rules_version"] != RULES_VERSION or not isinstance(value["stocks"], dict):
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
        return value
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise StateError(f"STATE_READ_ERROR: refusing to reset {path}: {exc}") from exc


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


def save(path, value):
    """Caller holds lock. Validate candidate, back up valid old state, commit once."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(".candidate.json")
    try:
        old = load(path)  # Refuse to back up or overwrite corrupt existing state.
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
        os.replace(candidate, path)
        sync_directory(path.parent)
    finally:
        if candidate.exists():
            candidate.unlink()


def recover(path, backup):
    """Explicit selected backup only; never silently choose or reset state."""
    path, backup = Path(path), Path(backup)
    envelope = json.loads(backup.read_text())
    value = envelope["state"]
    if envelope["state_hash"] != fingerprint(value) or envelope["backup_version"] != value.get("commit_version", 0):
        raise StateError("BACKUP_INTEGRITY_ERROR")
    with lock(path):
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
        finally:
            if candidate.exists():
                candidate.unlink()
    return {"recovered": True, "backup": str(backup), "state_hash": fingerprint(value)}
