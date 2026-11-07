"""Market Indices: strict Adj Close prices; independent of equity identities."""
import datetime as dt
import hashlib
import http.client
import json
import math
from pathlib import Path
import socket
import ssl
import time
import urllib.parse

import market_calendar as calendar
import test_yahoo_nine as transport
from src import indicators, state

SYMBOLS = ("^GSPC", "^NDX", "^SOX")
CATEGORY = "Market Indices"
NAMES = {"^GSPC": ("S&P 500",), "^NDX": ("NASDAQ 100", "NASDAQ-100"),
         "^SOX": ("PHLX Semiconductor", "PHLX Semiconductor Sector")}
VENUES = {"^GSPC": ("SNP", "SNP"), "^NDX": ("NIM", "Nasdaq GIDS"), "^SOX": ("NIM", "Nasdaq GIDS")}
IDENTITY_SOURCES = {"^GSPC": "https://www.spglobal.com/spdji/en/indices/equity/sp-500/",
                    "^NDX": "https://indexes.nasdaq.com/Index/Overview/NDX",
                    "^SOX": "https://indexes.nasdaq.com/Index/Overview/SOX"}


def validate(symbol, payload, as_of):
    if symbol not in SYMBOLS or as_of.tzinfo is None:
        raise ValueError("INDEX_UNIVERSE_OR_TIMEZONE_ERROR")
    if not isinstance(payload, dict) or not isinstance(payload.get("chart"), dict):
        raise ValueError("DATA_QUALITY_ERROR: chart structure")
    chart = payload["chart"]
    if chart.get("error") or not isinstance(chart.get("result"), list) or len(chart["result"]) != 1:
        raise ValueError("DATA_QUALITY_ERROR: chart result")
    result = chart["result"][0]
    if not isinstance(result, dict):
        raise ValueError("DATA_QUALITY_ERROR: result structure")
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    checks = {"symbol": meta.get("symbol") == symbol, "instrumentType": meta.get("instrumentType") == "INDEX",
              "currency": meta.get("currency") == "USD", "exchange": (meta.get("exchangeName"), meta.get("fullExchangeName")) == VENUES[symbol],
              "timezone": meta.get("exchangeTimezoneName") == "America/New_York",
              "name": (meta.get("longName") or meta.get("shortName")) in NAMES[symbol]}
    if not all(checks.values()):
        raise ValueError("IDENTITY_MISMATCH: " + json.dumps(checks))
    groups = result.get("indicators") if isinstance(result.get("indicators"), dict) else {}
    adjgroup = groups.get("adjclose") or []
    adj = adjgroup[0].get("adjclose") if adjgroup and isinstance(adjgroup[0], dict) else None
    if not isinstance(adj, list) or not adj:
        raise ValueError("MISSING_ADJCLOSE: Close fallback is forbidden; independent price-series policy needs approval")
    quotes = groups.get("quote")
    quote = quotes[0] if isinstance(quotes,list) and quotes and isinstance(quotes[0],dict) else {}
    close, stamps = quote.get("close"), result.get("timestamp")
    if not isinstance(close, list) or not isinstance(stamps, list) or not len(stamps) == len(adj) == len(close):
        raise ValueError("DATA_QUALITY_ERROR: timestamp/Adj Close/Close length mismatch")
    target = calendar.latest_completed_session(as_of).isoformat()
    pairs, closes, excluded, seen = [], {}, [], set()
    for stamp, a, c in zip(stamps, adj, close):
        if not transport.finite_number(stamp):
            raise ValueError("DATA_QUALITY_ERROR: timestamp")
        instant = dt.datetime.fromtimestamp(stamp, calendar.NY)
        day = instant.date(); name = day.isoformat(); bounds = calendar.session_bounds(day)
        if name in seen or not bounds or not bounds[0] <= instant <= bounds[1]:
            raise ValueError("DATA_QUALITY_ERROR: duplicate date or irregular session timestamp")
        seen.add(name)
        if as_of < bounds[1]:
            excluded.append(name)  # A live unfinished bar may contain null fields.
            continue
        if not transport.positive_price(a) or not transport.positive_price(c):
            raise ValueError("DATA_QUALITY_ERROR: null/NaN/infinite/nonpositive complete price")
        pairs.append((name, float(a))); closes[name] = float(c)
    indicators.validate_series(pairs, target)
    if len(pairs) < 252:
        raise ValueError("INSUFFICIENT_HISTORY: index has no young-listing exception")
    volume = quote.get("volume")
    relation = [a-closes[day] for day, a in pairs]
    identity = {k: meta.get(k) for k in ("symbol", "longName", "shortName", "instrumentType", "currency", "exchangeName", "fullExchangeName", "exchangeTimezoneName")}
    return {"symbol": symbol, "category": CATEGORY, "series_basis": "YAHOO_CHART_ADJCLOSE", "as_of_utc": as_of.isoformat(),
            "identity": identity, "identity_checks": checks, "pairs": pairs, "closes": closes, "target": target,
            "data_quality": "PASS", "valid_adjclose_count": len(pairs), "earliest_trading_date": pairs[0][0],
            "latest_trading_date": pairs[-1][0], "excluded_incomplete_dates": excluded,
            "close_adjclose_exact_equal": all(v == 0 for v in relation), "max_absolute_close_adjclose_difference": max(map(abs, relation)),
            "volume_missing_or_null_count": len(stamps) if not isinstance(volume, list) else sum(v is None for v in volume),
            "volume_zero_count": sum(v == 0 for v in volume) if isinstance(volume, list) else 0,
            "volume_policy": "Optional index metadata; never a price-validity prerequisite", "identity_source": IDENTITY_SOURCES[symbol],
            "venue_policy": "Exact Yahoo vendor dissemination codes, distinct from listing venue of constituent equities",
            "left_boundary_limit": "Internal exchange-session coverage verified; exact vendor range=2y boundary not independently certified"}


def read_samples(directory):
    directory = Path(directory)
    ledger = json.loads((directory / "collection_ledger.json").read_text())
    if [row["symbol"] for row in ledger["stocks"]] != list(SYMBOLS):
        raise ValueError("INDEX_COLLECTION_UNIVERSE_ERROR")
    items, errors = {}, {}
    for row in ledger["stocks"]:
        try:
            if row["http_status"] != 200:
                raise ValueError(row["error_category"] or "HTTP_ERROR")
            path = directory / Path(row["raw_file"]).name
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != row["response_sha256"]:
                raise ValueError("RAW_INDEX_EVIDENCE_HASH_MISMATCH")
            items[row["symbol"]] = validate(row["symbol"], json.loads(raw), dt.datetime.fromisoformat(row["as_of_utc"]))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors[row["symbol"]] = str(exc)
    return items, errors


def collect(directory):
    """One durable claim, at most three serial requests, never retries."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    ledger = directory / "collection_ledger.json"
    with state.lock(ledger):
        if ledger.exists():
            raise ValueError("COLLECTION_ALREADY_CLAIMED: inspect saved evidence; do not retry")
        report = {"category": CATEGORY, "started_at_utc": transport.utc_now().isoformat(), "claimed": True,
                  "status": "RUNNING", "parameters": transport.PARAMS, "retries": 0,
                  "http_request_count": 0, "stocks": [], "request_intervals": []}
        state.durable_json(ledger, report)
        scheduler = transport.RequestScheduler()
        stopped = None
        for symbol in SYMBOLS:
            row = transport.new_row(symbol, 1)
            report["stocks"].append(row)
            if stopped:
                row.update(status="SKIPPED", error_category=stopped, error_message="No request after global access stop")
                state.durable_json(ledger, report)
                continue
            connection = None
            try:
                addresses = socket.getaddrinfo(transport.HOST, 443, type=socket.SOCK_STREAM)
                row["dns"] = {"success": bool(addresses)}
                connection = http.client.HTTPSConnection(transport.HOST, timeout=transport.TIMEOUT_SECONDS, context=ssl.create_default_context())
                scheduler.begin(row)
                row["http_request_count"] = 1
                report["http_request_count"] += 1
                state.durable_json(ledger, report)  # claimed before request; uncertain crashes cannot retry
                target = "/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?" + urllib.parse.urlencode(transport.PARAMS)
                connection.request("GET", target, headers={"User-Agent": "Market-Indices-Diagnostic/1.0 (Python standard library)",
                    "Accept": "application/json", "Accept-Encoding": "identity", "Connection": "close"})
                response = connection.getresponse()
                row["http_status"] = response.status
                row["retry_after"] = response.getheader("Retry-After")
                row["response_headers"] = {k: response.getheader(k) for k in ("Date", "Content-Type", "Retry-After") if response.getheader(k)}
                raw = response.read()
                path = directory / (symbol[1:] + ".json")
                path.write_bytes(raw)
                row.update(raw_file=str(path.resolve()), response_sha256=hashlib.sha256(raw).hexdigest(), response_bytes=len(raw))
                if response.status != 200:
                    row["error_category"] = {401: "HTTP_UNAUTHORIZED", 403: "HTTP_FORBIDDEN", 429: "RATE_LIMITED"}.get(response.status, "HTTP_ERROR")
                    if response.status in (401, 403, 429):
                        stopped = row["error_category"]
                else:
                    try:
                        payload = json.loads(raw)
                        chart = payload.get("chart") if isinstance(payload, dict) else None
                        results = chart.get("result") if isinstance(chart, dict) else None
                        row["returned_meta"] = results[0].get("meta", {}) if isinstance(results, list) and results and isinstance(results[0], dict) else {}
                    except (ValueError, TypeError, KeyError) as exc:
                        row.update(error_category="INVALID_JSON", error_message=str(exc))
            except (OSError, http.client.HTTPException) as exc:
                transport.network_error(row, exc, "DNS" if isinstance(exc, socket.gaierror) else "HTTPS")
                if any(e.get("local_permission_denied") for e in row["errors"]):
                    stopped = "LOCAL_PERMISSION_DENIED"
            finally:
                if connection:
                    connection.close()
                row["request_end_utc"] = transport.utc_now().isoformat()
                row["as_of_utc"] = row["request_end_utc"]
                if row["request_start_monotonic"] is not None:
                    row["elapsed_seconds"] = time.monotonic() - row["request_start_monotonic"]
                row["status"] = "CAPTURED" if row["http_status"] == 200 and not row["error_category"] else "FAIL"
                report["request_intervals"] = scheduler.intervals
                state.durable_json(ledger, report)
                print(json.dumps({k: row.get(k) for k in ("symbol", "http_status", "error_category", "elapsed_seconds")}), flush=True)
        report.update(status="COMPLETED", finished_at_utc=transport.utc_now().isoformat(), rate_limited=stopped == "RATE_LIMITED")
        state.durable_json(ledger, report)
        return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", type=Path, required=True)
    collect(parser.parse_args().collect)
