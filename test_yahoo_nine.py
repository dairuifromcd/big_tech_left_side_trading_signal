#!/usr/bin/env python3
"""Phase 2: nine serial Yahoo Chart requests, no retries or trading signals.

Run: .venv/bin/python test_yahoo_nine.py
The compact diagnostic and separate timestamp/Close/Adj Close evidence are
checkpointed atomically after every symbol. Only Python's standard library is used.
"""

import argparse
import datetime as dt
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import platform
import re
import socket
import ssl
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo

import market_calendar as calendar
from test_yahoo_nvda import HOST, PARAMS, TIMEOUT_SECONDS, classify_network_error


BATCHES = (("NVDA", "AAPL", "GOOGL"), ("MSFT", "AMZN", "SPCX"),
           ("META", "AVGO", "TSLA"))
REQUEST_START_INTERVAL_SECONDS = 5.0
BATCH_EXTRA_WAIT_SECONDS = 30.0
GLOBAL_ACCESS_DENIAL_THRESHOLD = 2
USER_AGENT = "Yahoo-Nine-Stock-Diagnostic/2.0 (Python standard library)"
NY = ZoneInfo("America/New_York")
BRISBANE = ZoneInfo("Australia/Brisbane")
SPCX_IPO_DATE = dt.date(2026, 6, 12)
SPCX_SOURCES = [
    "https://m.nasdaqtrader.com/TraderNews.aspx?id=DTN2026-8",
    "https://ir.spacex.com/updates/releases-details/2026/Space-Exploration-Technologies-Corp--Announces-Pricing-of-Initial-Public-Offering/default.aspx?linkId=95",
]
NAME_ALIASES = {
    "NVDA": ("NVIDIA Corporation", "NVIDIA Corp"),
    "AAPL": ("Apple Inc",),
    "GOOGL": ("Alphabet Inc",),
    "MSFT": ("Microsoft Corporation", "Microsoft Corp"),
    "AMZN": ("Amazon.com Inc",),
    "SPCX": ("Space Exploration Technologies Corp", "Space Exploration Technologies Corporation", "SpaceX"),
    "META": ("Meta Platforms Inc",),
    "AVGO": ("Broadcom Inc",),
    "TSLA": ("Tesla Inc",),
}
IDENTITY_SOURCES = {
    "NVDA": "https://investor.nvidia.com/investor-resources/faqs/default.aspx",
    "AAPL": "https://investor.apple.com/investor-relations/faq/default.aspx",
    "GOOGL": "https://abc.xyz/investor/",
    "MSFT": "https://www.microsoft.com/en-us/investor/faq",
    "AMZN": "https://ir.aboutamazon.com/faqs/default.aspx",
    "SPCX": SPCX_SOURCES[0],
    "META": "https://investor.atmeta.com/resources/default.aspx",
    "AVGO": "https://investors.broadcom.com/company-information/faqs",
    "TSLA": "https://ir.tesla.com/",
}


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def finite_number(value):
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        return False


def positive_price(value):
    return finite_number(value) and value > 0


def add_error(row, category, message, **evidence):
    row["errors"].append({"category": category, "message": message, **evidence})
    if row["error_category"] is None:
        row["error_category"] = category
        row["error_message"] = message


def network_error(row, exc, phase):
    # Reuse the corrected SSL-first classification from the single-stock test.
    temporary = {"errors": []}
    classify_network_error(temporary, exc, phase)
    error = temporary["errors"][0]
    category = {
        "tls_error": "TLS_ERROR", "dns_error": "DNS_ERROR",
        "timeout": "TIMEOUT", "connection_failed": "CONNECTION_ERROR",
        "network_permission_denied": "CONNECTION_ERROR",
    }[error["category"]]
    add_error(row, category, error["message"], exception_type=error["exception_type"],
              exception_message=error["exception_message"], errno=error["errno"],
              local_permission_denied=error["category"] == "network_permission_denied")


def new_row(symbol, batch):
    return {
        "symbol": symbol, "batch": batch, "status": "PENDING",
        "request_start_utc": None, "request_end_utc": None,
        "request_start_monotonic": None, "request_end_monotonic": None,
        "elapsed_seconds": None, "http_status": None, "http_request_count": 0,
        "valid_adjclose_count": None, "earliest_trading_date": None,
        "latest_trading_date": None, "expected_trading_date": None,
        "latest_adjclose": None, "missing_count": None, "duplicate_count": None,
        "identity_validated": False, "calendar_validated": False,
        "data_quality_pass": False, "has_at_least_252_valid_days": False,
        "indicator_history_ready": False, "error_category": None,
        "error_message": None, "errors": [],
    }


class RequestScheduler:
    def __init__(self, request_guard=None):
        self.request_guard = request_guard
        self.last_start = None
        self.last_batch = None
        self.last_symbol = None
        self.intervals = []

    @staticmethod
    def sleep_until(deadline):
        start = time.monotonic()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return time.monotonic() - start
            time.sleep(remaining)

    def begin(self, row):
        normal_wait = 0.0
        extra_wait = 0.0
        boundary = self.last_batch is not None and self.last_batch != row["batch"]
        if self.last_start is not None:
            normal_wait = self.sleep_until(self.last_start + REQUEST_START_INTERVAL_SECONDS)
        if boundary:
            print(f"Batch {self.last_batch} -> {row['batch']}: extra {BATCH_EXTRA_WAIT_SECONDS:g}s wait", flush=True)
            extra_wait = self.sleep_until(time.monotonic() + BATCH_EXTRA_WAIT_SECONDS)
        if self.request_guard is not None:
            self.request_guard(row)  # Caller may stop safely after a long wait, before request().
        start = time.monotonic()
        row["request_start_monotonic"] = start
        row["request_start_utc"] = utc_now().isoformat()
        if self.last_start is not None:
            self.intervals.append({
                "previous_symbol": self.last_symbol, "symbol": row["symbol"],
                "batch_boundary": boundary, "start_gap_seconds": start - self.last_start,
                "normal_wait_seconds": normal_wait, "batch_extra_wait_seconds": extra_wait,
                "minimum_start_gap_seconds": REQUEST_START_INTERVAL_SECONDS + (BATCH_EXTRA_WAIT_SECONDS if boundary else 0),
                "interval_pass": start - self.last_start >= REQUEST_START_INTERVAL_SECONDS + (BATCH_EXTRA_WAIT_SECONDS if boundary else 0),
                "batch_wait_pass": not boundary or extra_wait >= BATCH_EXTRA_WAIT_SECONDS,
            })
        self.last_start, self.last_batch, self.last_symbol = start, row["batch"], row["symbol"]


def normalized_name(value):
    text = str(value or "").lower()
    text = re.sub(r"\b(class\s+a|common stock|ordinary shares)\b", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def validate_identity(row, meta):
    name = meta.get("longName") or meta.get("shortName")
    checks = {
        "symbol": meta.get("symbol") == row["symbol"],
        "company_name": normalized_name(name) in {normalized_name(n) for n in NAME_ALIASES[row["symbol"]]},
        "instrument_type": meta.get("instrumentType") == "EQUITY",
        "currency": meta.get("currency") == "USD",
        "exchange": meta.get("exchangeName") == "NMS" and meta.get("fullExchangeName") in ("NasdaqGS", "Nasdaq Global Select Market", "NASDAQ Global Select Market"),
        "timezone": meta.get("exchangeTimezoneName") == "America/New_York",
    }
    row["identity"] = {key: meta.get(key) for key in (
        "symbol", "longName", "shortName", "instrumentType", "exchangeName",
        "fullExchangeName", "currency", "exchangeTimezoneName", "firstTradeDate")}
    if row["symbol"] == "SPCX":
        row["identity"]["expected_ipo_date"] = SPCX_IPO_DATE.isoformat()
        row["identity"]["sources"] = SPCX_SOURCES
        stamp = meta.get("firstTradeDate")
        if stamp is not None:
            try:
                first_date = dt.datetime.fromtimestamp(stamp, NY).date() if finite_number(stamp) else None
            except (ValueError, OverflowError, OSError):
                first_date = None
            row["identity"]["first_trade_date_new_york"] = first_date.isoformat() if first_date else None
            checks["first_trade_date"] = first_date == SPCX_IPO_DATE
    row["identity"]["checks"] = checks
    row["identity_validated"] = all(checks.values())
    if not row["identity_validated"]:
        add_error(row, "IDENTITY_MISMATCH", "证券身份未通过：" + ", ".join(key for key, passed in checks.items() if not passed))


def analyze_payload(row, payload, as_of):
    """Return separate price evidence; keep the diagnostic itself compact."""
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict) or chart.get("error"):
        add_error(row, "DATA_QUALITY_ERROR", "chart 对象缺失或返回接口错误。", chart_error=chart.get("error") if isinstance(chart, dict) else None)
        return {"symbol": row["symbol"], "rows": []}
    results = chart.get("result")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        add_error(row, "DATA_QUALITY_ERROR", "预期一个 chart.result 股票结果。")
        return {"symbol": row["symbol"], "rows": []}
    result = results[0]
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    validate_identity(row, meta)
    try:
        expected = calendar.latest_completed_session(as_of)
        row["expected_trading_date"] = expected.isoformat()
        row["expected_session_close_utc"] = calendar.session_bounds(expected)[1].astimezone(dt.timezone.utc).isoformat()
        row["calendar_validated"] = True
    except (ValueError, KeyError) as exc:
        expected = None
        add_error(row, "DATA_QUALITY_ERROR", "日历验证未通过，不能确认最新完整交易日。", calendar_error=str(exc))
    timestamps = result.get("timestamp")
    timestamps = timestamps if isinstance(timestamps, list) else []
    indicators = result.get("indicators")
    indicators = indicators if isinstance(indicators, dict) else {}
    adj_groups = indicators.get("adjclose")
    quote_groups = indicators.get("quote")
    adj = adj_groups[0].get("adjclose") if isinstance(adj_groups, list) and adj_groups and isinstance(adj_groups[0], dict) else None
    close = quote_groups[0].get("close") if isinstance(quote_groups, list) and quote_groups and isinstance(quote_groups[0], dict) else None
    row["has_adjclose"] = isinstance(adj, list) and bool(adj)
    if not row["has_adjclose"]:
        add_error(row, "MISSING_ADJCLOSE", "缺少非空 indicators.adjclose[0].adjclose 数组。")
    adj = adj if isinstance(adj, list) else []
    close = close if isinstance(close, list) else []
    row["array_lengths"] = {"timestamp": len(timestamps), "adjclose": len(adj), "close": len(close)}
    row["array_lengths_match"] = len(timestamps) == len(adj) == len(close)
    if not timestamps or not row["array_lengths_match"]:
        add_error(row, "DATA_QUALITY_ERROR", "时间戳、Adj Close、Close 数组缺失或长度不一致。")
    series, complete, seen = [], {}, set()
    missing = duplicate = bad_close = bad_stamp = bad_session = incomplete = pre_ipo = 0
    numeric_valid = 0
    for index in range(max(len(timestamps), len(adj), len(close))):
        stamp = timestamps[index] if index < len(timestamps) else None
        price = adj[index] if index < len(adj) else None
        raw_close = close[index] if index < len(close) else None
        day, instant, bounds = None, None, None
        flags = []
        if finite_number(stamp):
            try:
                instant = dt.datetime.fromtimestamp(stamp, NY)
                day = instant.date()
            except (ValueError, OverflowError, OSError):
                pass
        if day is None:
            bad_stamp += 1
            flags.append("INVALID_TIMESTAMP")
        else:
            if day in seen:
                duplicate += 1
                flags.append("DUPLICATE_DATE")
            seen.add(day)
            if row["symbol"] == "SPCX" and day < SPCX_IPO_DATE:
                pre_ipo += 1
            try:
                bounds = calendar.session_bounds(day)
            except ValueError:
                row["calendar_validated"] = False
            if bounds is None or not (bounds[0] <= instant <= bounds[1]):
                bad_session += 1
                flags.append("INVALID_REGULAR_SESSION_TIMESTAMP")
            elif as_of < bounds[1]:
                incomplete += 1
                flags.append("INCOMPLETE_SESSION_EXCLUDED")
        if not positive_price(price):
            missing += 1
            flags.append("INVALID_ADJCLOSE")
        if not positive_price(raw_close):
            bad_close += 1
            flags.append("INVALID_CLOSE")
        if day is not None and positive_price(price):
            numeric_valid += 1
            if bounds and bounds[0] <= instant <= bounds[1] and as_of >= bounds[1]:
                complete[day] = float(price)
        series.append({
            "timestamp": stamp if finite_number(stamp) else None,
            "trading_date": day.isoformat() if day else None,
            "adjclose": float(price) if finite_number(price) else None,
            "close": float(raw_close) if finite_number(raw_close) else None,
            "regular_session_completed": bool(bounds and as_of >= bounds[1]),
            "flags": flags,
        })
    if pre_ipo:
        row["identity_validated"] = False
        row["identity"]["pre_ipo_row_count"] = pre_ipo
        row["identity"]["checks"]["no_pre_ipo_history"] = False
        # Identity contamination takes priority over numerical history checks.
        add_error(row, "IDENTITY_MISMATCH", f"SPCX 有 {pre_ipo} 条早于独立核实上市日期的记录，疑似代码复用污染。")
        row["error_category"] = "IDENTITY_MISMATCH"
        row["error_message"] = row["errors"][-1]["message"]
    row.update({
        "raw_numeric_valid_sample_count": numeric_valid,
        "observed_complete_adjclose_count": len(complete),
        "valid_adjclose_count": len(complete) if row["identity_validated"] else 0,
        "missing_count": missing, "duplicate_count": duplicate,
        "invalid_close_count": bad_close, "invalid_timestamp_count": bad_stamp,
        "invalid_regular_session_count": bad_session,
        "incomplete_session_row_count": incomplete,
        "latest_returned_trading_date": max(seen).isoformat() if seen else None,
        "latest_returned_row_is_completed_regular_session": bool(series and series[-1]["regular_session_completed"] and not any(flag in series[-1]["flags"] for flag in ("INVALID_TIMESTAMP", "INVALID_REGULAR_SESSION_TIMESTAMP"))),
    })
    if missing or duplicate or bad_close or bad_stamp or bad_session:
        add_error(row, "DATA_QUALITY_ERROR", "存在无效价格、时间戳、重复日期或异常常规交易时段记录。")
    if not row["calendar_validated"] and not any(e["message"].startswith("日历验证") for e in row["errors"]):
        add_error(row, "DATA_QUALITY_ERROR", "日历验证未通过：历史日期超出核实范围。")
    if complete:
        dates = sorted(complete)
        row["earliest_trading_date"], row["latest_trading_date"] = dates[0].isoformat(), dates[-1].isoformat()
        row["latest_adjclose"] = complete[dates[-1]]
        row["has_at_least_252_valid_days"] = len(complete) >= 252 and row["identity_validated"]
    if expected is not None:
        row["includes_expected_trading_date"] = expected in complete
        if expected not in complete:
            add_error(row, "STALE_DATA", f"缺少最新完整交易日 {expected} 的有效 Adj Close。")
        # Validate complete requested history; never infer a new listing from count alone.
        known_ipo = SPCX_IPO_DATE if row["symbol"] == "SPCX" and row["identity_validated"] else None
        # Yahoo's rolling range boundary is not necessarily midnight New York.
        # Check internal calendar gaps from the returned start, without inventing
        # a missing first day based on an undocumented range rounding rule.
        history_start = known_ipo or (min(complete) if complete else expected)
        row["history_expected_start"] = history_start.isoformat()
        row["history_start_method"] = "Independent IPO date" if known_ipo else "Earliest returned complete session; two-year left boundary not independently certified"
        try:
            expected_dates = calendar.sessions_between(history_start, expected)
            missing_dates = sorted(set(expected_dates) - complete.keys())
            row["expected_history_session_count"] = len(expected_dates)
            row["missing_expected_session_count"] = len(missing_dates)
            row["missing_expected_session_examples"] = [day.isoformat() for day in missing_dates[:10]]
            if missing_dates:
                add_error(row, "DATA_QUALITY_ERROR", f"请求范围内缺少 {len(missing_dates)} 个预期交易日。")
            known_short = bool(known_ipo and len(expected_dates) < 252 and not missing_dates)
        except ValueError as exc:
            known_short = False
            row["calendar_validated"] = False
            add_error(row, "DATA_QUALITY_ERROR", "日历验证未通过，无法核对历史交易日。", calendar_error=str(exc))
        row["history_status"] = "EXPECTED_SHORT_IPO_HISTORY" if known_short else (
            "SUFFICIENT_HISTORY" if row["has_at_least_252_valid_days"] else "INSUFFICIENT_HISTORY_UNEXPLAINED")
        if not row["has_at_least_252_valid_days"] and not known_short:
            add_error(row, "INSUFFICIENT_HISTORY", "有效历史不足 252 日，未证实为完整的新上市历史。")
        row["short_history_explained"] = known_short
    row["indicator_history_ready"] = row["has_at_least_252_valid_days"] and not row["errors"]
    row["data_quality_pass"] = row["identity_validated"] and row["calendar_validated"] and not row["errors"]
    return {"symbol": row["symbol"], "identity_validated": row["identity_validated"],
            "as_of_utc": as_of.isoformat(), "rows": series}


def collect_symbol(row, scheduler):
    evidence = {"symbol": row["symbol"], "rows": []}
    row["collection_start_utc"] = utc_now().isoformat()
    row["status"] = "RUNNING"
    connection = None
    dns_start = time.monotonic()
    try:
        addresses = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise socket.gaierror("DNS returned no addresses")
        row["dns"] = {"success": True, "addresses": sorted({r[4][0] for r in addresses})}
    except OSError as exc:
        row["dns"] = {"success": False}
        network_error(row, exc, "DNS")
    row["dns"]["elapsed_seconds"] = time.monotonic() - dns_start
    if row["dns"]["success"]:
        try:
            target = "/v8/finance/chart/" + row["symbol"] + "?" + urllib.parse.urlencode(PARAMS)
            connection = http.client.HTTPSConnection(HOST, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
            scheduler.begin(row)
            row["http_request_count"] = 1
            connection.request("GET", target, headers={
                "User-Agent": USER_AGENT, "Accept": "application/json",
                "Accept-Encoding": "identity", "Connection": "close"})
            response = connection.getresponse()
            row["http_status"] = response.status
            row["response_headers"] = {name: response.getheader(name) for name in (
                "Date", "Content-Type", "Retry-After", "Cache-Control") if response.getheader(name) is not None}
            row["retry_after"] = response.getheader("Retry-After")
            if response.status != 200:
                category = {429: "RATE_LIMITED", 401: "HTTP_UNAUTHORIZED", 403: "HTTP_FORBIDDEN"}.get(response.status, "HTTP_ERROR")
                add_error(row, category, f"HTTP {response.status} {response.reason}; 未重试。")
            raw = response.read()
            row["request_end_monotonic"] = time.monotonic()
            row["request_end_utc"] = utc_now().isoformat()
            row["elapsed_seconds"] = row["request_end_monotonic"] - row["request_start_monotonic"]
            row["response_bytes"] = len(raw)
            row["response_sha256"] = hashlib.sha256(raw).hexdigest()
            row["response_complete"] = True
            if response.status != 200:
                row["error_body_excerpt"] = raw.decode("utf-8", errors="replace")[:512]
            else:
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeDecodeError) as exc:
                    add_error(row, "INVALID_JSON", str(exc))
                    row["error_body_excerpt"] = raw.decode("utf-8", errors="replace")[:512]
                else:
                    evidence = analyze_payload(row, payload, utc_now())
        except (OSError, http.client.HTTPException) as exc:
            network_error(row, exc, "HTTPS")
        finally:
            if row["request_start_monotonic"] is not None and row["request_end_monotonic"] is None:
                row["request_end_monotonic"] = time.monotonic()
                row["request_end_utc"] = utc_now().isoformat()
                row["elapsed_seconds"] = row["request_end_monotonic"] - row["request_start_monotonic"]
            if connection is not None:
                connection.close()
    if row["expected_trading_date"] is None:
        try:
            row["expected_trading_date"] = calendar.latest_completed_session(utc_now()).isoformat()
            row["calendar_validated"] = True
        except ValueError as exc:
            add_error(row, "DATA_QUALITY_ERROR", "日历验证未通过。", calendar_error=str(exc))
    row["status"] = "PASS" if row["data_quality_pass"] else "FAIL"
    row["collection_end_utc"] = utc_now().isoformat()
    return evidence


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def update_summary(report, scheduler, started_monotonic):
    rows = report["stocks"]
    report["actual_http_request_count"] = sum(row["http_request_count"] for row in rows)
    report["http_200_count"] = sum(row["http_status"] == 200 for row in rows)
    report["http_response_count"] = sum(row["http_status"] is not None for row in rows)
    report["success_count"] = sum(row["status"] == "PASS" for row in rows)
    report["failure_count"] = sum(row["status"] == "FAIL" for row in rows)
    report["skipped_count"] = sum(row["status"].startswith("SKIPPED") for row in rows)
    report["rate_limited"] = any(row["http_status"] == 429 for row in rows)
    report["request_intervals"] = scheduler.intervals
    report["timing_pass"] = all(item["interval_pass"] and item["batch_wait_pass"] for item in scheduler.intervals)
    report["batch_extra_wait_count"] = sum(item["batch_boundary"] for item in scheduler.intervals)
    report["elapsed_seconds"] = time.monotonic() - started_monotonic
    report["last_updated_at_utc"] = utc_now().isoformat()
    report["all_nine_have_explicit_results"] = all(row["status"] != "PENDING" and row["status"] != "RUNNING" for row in rows)
    report["all_data_quality_pass"] = report["success_count"] == 9
    report["all_indicator_history_ready"] = all(row["indicator_history_ready"] for row in rows)


def run(output_dir=None, execution_context="local-terminal-or-unspecified", request_guard=None):
    started_monotonic = time.monotonic()
    started = utc_now()
    output_dir = Path(output_dir) if output_dir else Path(__file__).resolve().parent / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.astimezone(BRISBANE).strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"yahoo_nine_diagnostic_{stamp}.json"
    data_path = output_dir / f"yahoo_nine_prices_{stamp}.json"
    if report_path.exists() or data_path.exists():
        raise FileExistsError("Report timestamp already exists; refusing to overwrite prior evidence.")
    report = {
        "schema_version": 1, "phase": 2, "started_at_utc": started.isoformat(),
        "started_at_brisbane": started.astimezone(BRISBANE).isoformat(), "finished_at_utc": None,
        "environment": {"python_version": sys.version, "python_executable": sys.executable,
                        "virtual_environment": sys.prefix != sys.base_prefix,
                        "platform": platform.platform(), "tls_library": ssl.OPENSSL_VERSION,
                        "execution_context": execution_context,
                        "ssl_default_verify_paths": ssl.get_default_verify_paths()._asdict()},
        "configuration": {"host": HOST, "path": "/v8/finance/chart/{symbol}", "parameters": PARAMS.copy(),
                          "batches": [list(batch) for batch in BATCHES], "request_start_interval_seconds": REQUEST_START_INTERVAL_SECONDS,
                          "batch_extra_wait_seconds": BATCH_EXTRA_WAIT_SECONDS, "timeout_seconds": TIMEOUT_SECONDS,
                          "requests_per_stock": 1, "retries": 0, "proxy": False, "follow_redirects": False,
                          "user_agent": USER_AGENT, "global_access_denial_threshold": GLOBAL_ACCESS_DENIAL_THRESHOLD,
                          "rate_limit_note": "Conservative test intervals only; not an official Yahoo quota or availability guarantee.",
                          "count_definition": "One http.client.request() invocation per attempted symbol; failed DNS causes zero invocations.",
                          "interval_definition": "Monotonic request() invocation starts; first satisfy normal start interval, then sleep an additional batch wait."},
        "calendar": calendar.calendar_metadata(), "identity_sources": IDENTITY_SOURCES,
        "price_evidence_file": str(data_path.resolve()), "report_file": str(report_path.resolve()),
        "stocks": [new_row(symbol, batch) for batch, symbols in enumerate(BATCHES, 1) for symbol in symbols],
        "overall_conclusion": "RUNNING", "stop_reason": None,
        "limitations": [
            "Two-year rolling range left boundary is not independently certified; calendar gaps from first returned session onward are checked.",
            "Expected completed session is evaluated per symbol at response time; provider prices may be revised after collection.",
            "An incomplete current session is retained as evidence but excluded from all completed-day counts and latest prices.",
        ],
    }
    try:
        expected_start = calendar.latest_completed_session(started).isoformat()
        report["calendar"]["validation_pass"] = True
        report["calendar"]["expected_trading_date_at_start"] = expected_start
        for row in report["stocks"]:
            row["expected_trading_date"] = expected_start
            row["calendar_validated"] = True
    except ValueError as exc:
        report["calendar"]["validation_pass"] = False
        report["calendar"]["error"] = str(exc)
    evidence = {"schema_version": 1, "diagnostic_file": str(report_path.resolve()), "stocks": {}}
    scheduler = RequestScheduler(request_guard=request_guard)

    def checkpoint():
        update_summary(report, scheduler, started_monotonic)
        atomic_json(data_path, evidence)
        report["price_evidence_sha256"] = hashlib.sha256(data_path.read_bytes()).hexdigest()
        atomic_json(report_path, report)

    checkpoint()
    denied = 0
    previous_status = None
    try:
        for row in report["stocks"]:
            if report["stop_reason"]:
                row["status"] = "SKIPPED_RATE_LIMITED" if report["rate_limited"] else "SKIPPED_GLOBAL_RESTRICTION"
                skip_category = "RATE_LIMITED" if report["rate_limited"] else (
                    {401: "HTTP_UNAUTHORIZED", 403: "HTTP_FORBIDDEN"}.get(previous_status, "CONNECTION_ERROR"))
                add_error(row, skip_category,
                          "未发送请求：" + report["stop_reason"])
                checkpoint()
                continue
            evidence["stocks"][row["symbol"]] = collect_symbol(row, scheduler)
            previous_status = row["http_status"]
            if row["http_status"] == 429:
                report["stop_reason"] = "RATE_LIMITED: HTTP 429; all subsequent Yahoo requests stopped."
            denied = denied + 1 if row["http_status"] in (401, 403) else 0
            if denied >= GLOBAL_ACCESS_DENIAL_THRESHOLD:
                report["stop_reason"] = "Consecutive 401/403 responses on different symbols: conservative global access restriction stop."
            if any(error.get("local_permission_denied") for error in row["errors"]):
                report["stop_reason"] = "Local network permission denied; cannot assess Yahoo availability."
            checkpoint()
            print(f"Batch {row['batch']} {row['symbol']}: HTTP {row['http_status']}, valid={row['valid_adjclose_count']}, latest={row['latest_trading_date']}, {row['status']} {row['error_category'] or ''}", flush=True)
    except (KeyboardInterrupt, Exception) as exc:
        report["stop_reason"] = f"Interrupted/error: {type(exc).__name__}: {exc}"
        for row in report["stocks"]:
            if row["status"] in ("PENDING", "RUNNING"):
                row["status"] = "FAIL" if row["status"] == "RUNNING" else "SKIPPED_INTERRUPTED"
                add_error(row, "DATA_QUALITY_ERROR", report["stop_reason"])
    finally:
        report["finished_at_utc"] = utc_now().isoformat()
        update_summary(report, scheduler, started_monotonic)
        report["overall_conclusion"] = "RATE_LIMITED" if report["rate_limited"] else (
            "PASS_WITH_EXPECTED_SHORT_IPO_HISTORY" if report["all_data_quality_pass"] and not report["all_indicator_history_ready"] else (
                "PASS" if report["all_data_quality_pass"] else "FAIL_OR_PARTIAL"))
        checkpoint()
    print(json.dumps({key: report[key] for key in (
        "report_file", "price_evidence_file", "actual_http_request_count", "http_200_count",
        "success_count", "failure_count", "skipped_count", "rate_limited", "timing_pass",
        "elapsed_seconds", "overall_conclusion")}, ensure_ascii=False, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-context", default="local-terminal-or-unspecified")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = run(args.output_dir, args.execution_context)
    return 0 if result["all_data_quality_pass"] and result["timing_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
