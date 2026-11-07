#!/usr/bin/env python3
"""One-shot NVDA Chart API diagnostic; Python 3.9+ standard library only.

DNS runs first. At most one GET is attempted, with no retries, redirects,
proxies, cookies, or browser impersonation. The JSON report includes the full
response body. Freshness is assessed against 2026-10-27, not a holiday calendar.
range=2y tests the requested two years, not NVDA's entire listing history.
"""

import argparse
import datetime as dt
import errno
import http.client
import json
import math
from pathlib import Path
import platform
import socket
import ssl
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo


HOST = "query1.finance.yahoo.com"
PATH = "/v8/finance/chart/NVDA"
PARAMS = {
    "range": "2y",
    "interval": "1d",
    "events": "div,splits",
    "includeAdjustedClose": "true",
}
TARGET_DATE = "2026-10-27"
TIMEOUT_SECONDS = 20
USER_AGENT = "NVDA-AdjClose-Diagnostic/1.0 (Python standard library)"


def add_error(report, category, message, exception=None):
    error = {"category": category, "message": message}
    if exception is not None:
        error["exception_type"] = type(exception).__name__
        error["exception_message"] = str(exception)
        error["errno"] = getattr(exception, "errno", None)
    report["errors"].append(error)


def classify_network_error(report, exc, phase):
    # SSL error codes share integers with OS errno (e.g. SSL_ERROR_SSL == EPERM).
    # Classify SSL first so a certificate failure is never called a permission denial.
    if isinstance(exc, ssl.SSLError):
        category = "tls_error"
        message = f"{phase}: TLS 连接或证书验证失败。"
    elif isinstance(exc, PermissionError) or getattr(exc, "errno", None) in (
        errno.EPERM, errno.EACCES
    ):
        category = "network_permission_denied"
        message = f"{phase}: 网络操作被本地权限策略拒绝；不能据此判断 Yahoo 故障。"
    elif isinstance(exc, socket.gaierror):
        category = "dns_error"
        message = f"{phase}: 本地 DNS 解析失败；原因可能是解析器、网络或执行环境限制，不能归因于 Yahoo。"
    elif isinstance(exc, (TimeoutError, socket.timeout)):
        category = "timeout"
        message = f"{phase}: 网络操作超时。"
    else:
        category = "connection_failed"
        message = f"{phase}: 连接、发送或读取响应失败。"
    add_error(report, category, message, exc)


def analyze_data(report, payload):
    """Validate timestamp/adjusted-price pairs without falling back to Close."""
    metrics = report["metrics"]
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict):
        add_error(report, "data_missing", "响应缺少 chart 对象。")
        return
    if chart.get("error"):
        add_error(report, "api_error", "Yahoo chart.error: " + json.dumps(
            chart["error"], ensure_ascii=False))
        return
    results = chart.get("result")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        add_error(report, "data_missing", "chart.result 缺失或不是单个股票结果。")
        return
    result = results[0]
    meta = result.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    metrics["returned_symbol"] = meta.get("symbol")
    metrics["currency"] = meta.get("currency")
    metrics["exchange_timezone"] = meta.get("exchangeTimezoneName")
    if meta.get("symbol") != "NVDA":
        add_error(report, "data_missing", "响应中的 symbol 不是 NVDA。")
    timestamps = result.get("timestamp")
    timestamps = timestamps if isinstance(timestamps, list) else []
    metrics["timestamp_count"] = len(timestamps)
    indicators = result.get("indicators")
    indicators = indicators if isinstance(indicators, dict) else {}
    metrics["has_indicators_adjclose"] = "adjclose" in indicators
    groups = indicators.get("adjclose")
    prices = groups[0].get("adjclose") if (
        isinstance(groups, list) and groups and isinstance(groups[0], dict)
    ) else None
    if not isinstance(prices, list) or not timestamps:
        add_error(report, "data_missing", "缺少非空 timestamp 或 indicators.adjclose[0].adjclose 数组。")
        return
    metrics["adjclose_array_length"] = len(prices)
    metrics["array_lengths_match"] = len(timestamps) == len(prices)
    if not metrics["array_lengths_match"]:
        add_error(report, "data_missing", "timestamp 和 Adj Close 数组长度不一致。")

    ny = ZoneInfo("America/New_York")
    valid = {}
    invalid_count = 0
    duplicate_count = 0
    for index, stamp in enumerate(timestamps):
        price = prices[index] if index < len(prices) else None
        if (isinstance(stamp, bool) or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp) or isinstance(price, bool)
                or not isinstance(price, (int, float))
                or not math.isfinite(price) or price <= 0):
            invalid_count += 1
            continue
        try:
            date = dt.datetime.fromtimestamp(stamp, ny).date().isoformat()
        except (ValueError, OverflowError, OSError):
            invalid_count += 1
            continue
        if date in valid:
            duplicate_count += 1
        valid[date] = float(price)
    metrics["invalid_or_missing_sample_count"] = invalid_count
    metrics["duplicate_trading_date_count"] = duplicate_count
    metrics["unpaired_adjclose_count"] = max(0, len(prices) - len(timestamps))
    metrics["valid_adjclose_count"] = len(valid)
    metrics["has_at_least_252_valid_days"] = len(valid) >= 252
    metrics["covers_2026_10_27"] = TARGET_DATE in valid
    metrics["all_returned_rows_valid_and_unique"] = (
        bool(valid) and metrics["array_lengths_match"]
        and invalid_count == 0 and duplicate_count == 0
    )
    if invalid_count or duplicate_count:
        add_error(report, "data_missing", "返回序列存在无效/缺失 Adj Close 或重复交易日期。")
    if not valid:
        add_error(report, "data_missing", "没有有效 Adj Close 样本。")
        return
    dates = sorted(valid)
    metrics["earliest_trading_date"] = dates[0]
    metrics["latest_trading_date"] = dates[-1]
    metrics["latest_valid_adjclose"] = valid[dates[-1]]
    metrics["latest_observation_age_calendar_days"] = (
        dt.datetime.now(ny).date() - dt.date.fromisoformat(dates[-1])
    ).days
    metrics["data_stale_before_required_date"] = dates[-1] < TARGET_DATE
    if metrics["data_stale_before_required_date"]:
        add_error(report, "data_stale", f"最新有效交易日 {dates[-1]} 早于要求日期 {TARGET_DATE}。")
    elif not metrics["covers_2026_10_27"]:
        add_error(report, "data_missing", f"序列中缺少 {TARGET_DATE} 的有效 Adj Close。")
    if not metrics["has_at_least_252_valid_days"]:
        add_error(report, "data_missing", "有效交易日少于 252 个。")


def diagnose(execution_context):
    start = time.perf_counter()
    request_target = PATH + "?" + urllib.parse.urlencode(PARAMS)
    report = {
        "tested_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tested_at_local": dt.datetime.now().astimezone().isoformat(),
        "environment": {
            "execution_context": execution_context,
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "working_directory": str(Path.cwd()),
            "tls_library": ssl.OPENSSL_VERSION,
            "ssl_default_verify_paths": ssl.get_default_verify_paths()._asdict(),
        },
        "request": {
            "method": "GET", "symbol": "NVDA",
            "url": "https://" + HOST + request_target,
            "parameters": PARAMS.copy(), "user_agent": USER_AGENT,
            "socket_timeout_seconds": TIMEOUT_SECONDS,
            "max_http_requests": 1, "retries": 0,
            "follow_redirects": False, "use_proxy": False,
        },
        "dns": {"success": False, "addresses": [], "elapsed_seconds": None},
        "http": {
            "request_attempted": False, "request_invocations": 0,
            "status_code": None, "reason": None, "elapsed_seconds": None,
            "response_headers": {}, "response_byte_count": None,
            "response_complete": False, "response_json": None,
        },
        "metrics": {
            "has_indicators_adjclose": None, "valid_adjclose_count": None,
            "earliest_trading_date": None, "latest_trading_date": None,
            "latest_valid_adjclose": None, "covers_2026_10_27": None,
            "has_at_least_252_valid_days": None,
            "data_stale_before_required_date": None,
        },
        "freshness_policy": {
            "required_trading_date": TARGET_DATE,
            "description": "最新有效日期不得早于要求日期，且必须包含要求日期；不验证此后交易日的完整性。",
        },
        "limitations": [
            "range=2y 仅验证请求的两年区间，不是上市以来全部历史。",
            "可检查返回行的完整性；未用独立交易所日历逐日验证整个两年区间。",
            "最新日线可能属于尚未收盘的交易日；此测试不据此计算交易信号。",
        ],
        "success": False, "errors": [],
    }
    dns_start = time.perf_counter()
    try:
        records = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        report["dns"]["addresses"] = sorted({record[4][0] for record in records})
        if not records:
            raise socket.gaierror("DNS returned no addresses")
        report["dns"]["success"] = True
    except OSError as exc:
        classify_network_error(report, exc, "DNS")
    finally:
        report["dns"]["elapsed_seconds"] = round(time.perf_counter() - dns_start, 6)

    if report["dns"]["success"]:
        connection = None
        http_start = time.perf_counter()
        try:
            connection = http.client.HTTPSConnection(
                HOST, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
            report["http"]["request_attempted"] = True
            report["http"]["request_invocations"] = 1
            connection.request("GET", request_target, headers={
                "User-Agent": USER_AGENT, "Accept": "application/json",
                "Accept-Encoding": "identity", "Connection": "close",
            })
            response = connection.getresponse()
            report["http"]["status_code"] = response.status
            report["http"]["reason"] = response.reason
            report["http"]["response_headers"] = {
                name: response.getheader(name) for name in
                ("Date", "Content-Type", "Content-Length", "Retry-After", "Cache-Control")
                if response.getheader(name) is not None
            }
            if response.status != 200:
                category = f"http_{response.status}" if response.status in (401, 403, 429) else "http_error"
                add_error(report, category, f"HTTP {response.status} {response.reason}；未重试。")
            raw = response.read()
            report["http"]["response_byte_count"] = len(raw)
            report["http"]["response_complete"] = True
            try:
                payload = json.loads(raw)
                report["http"]["response_json"] = payload
            except (ValueError, UnicodeDecodeError) as exc:
                report["http"]["response_text"] = raw.decode("utf-8", errors="replace")
                add_error(report, "json_parse_error", "响应正文不是有效 JSON。", exc)
            else:
                if response.status == 200:
                    analyze_data(report, payload)
        except (OSError, http.client.HTTPException) as exc:
            classify_network_error(report, exc, "HTTPS")
        finally:
            report["http"]["elapsed_seconds"] = round(time.perf_counter() - http_start, 6)
            if connection is not None:
                connection.close()
    report["success"] = not report["errors"] and report["metrics"]["valid_adjclose_count"] is not None
    report["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["total_elapsed_seconds"] = round(time.perf_counter() - start, 6)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().with_name("test_yahoo_nvda_result.json"))
    parser.add_argument("--execution-context", default="local-terminal-or-unspecified",
                        help="Execution context label for provenance; does not change permissions.")
    args = parser.parse_args()
    # Check that the output can be created before spending the single request.
    with args.output.open("w", encoding="utf-8") as output:
        report = diagnose(args.execution_context)
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    # Keep console output concise; full response is retained in the JSON file.
    summary = {key: value for key, value in report.items() if key != "http"}
    summary["http"] = {key: value for key, value in report["http"].items()
                       if key not in ("response_json", "response_text")}
    summary["result_file"] = str(args.output.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
