"""Pure Adj Close calculations. Float64, no rounding until presentation."""
import datetime as dt
import math
from market_calendar import sessions_between

RULES_VERSION = "adjclose-wilder14-sma-252-v1"


def validate_series(rows, target):
    if not rows or rows[-1][0] != target:
        raise ValueError("STALE_DATA: target session missing")
    dates = [dt.date.fromisoformat(date) for date, _ in rows]
    if dates != sessions_between(dates[0], dates[-1]):
        raise ValueError("DATA_QUALITY_ERROR: unordered, duplicate or missing trading date")
    for _, price in rows:
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise ValueError("DATA_QUALITY_ERROR: invalid Adj Close")


def sma(prices, n):
    return math.fsum(prices[-n:]) / n if len(prices) >= n else None


def wilder_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    changes = [b - a for a, b in zip(prices, prices[1:])]
    gain = math.fsum(max(x, 0) for x in changes[:period]) / period
    loss = math.fsum(max(-x, 0) for x in changes[:period]) / period
    for change in changes[period:]:
        gain = (gain * (period - 1) + max(change, 0)) / period
        loss = (loss * (period - 1) + max(-change, 0)) / period
    if gain == loss == 0:
        return 50.0  # Explicit neutral convention for an entirely flat series.
    if loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1 + gain / loss)


def calculate(rows, target, allow_short=False):
    validate_series(rows, target)
    if len(rows) < 252 and not allow_short:
        raise ValueError("INSUFFICIENT_HISTORY: short listing not independently established")
    window = rows[-252:]
    # Exact equal maxima: latest date wins, deterministically.
    highest_date, highest = max(window, key=lambda row: (row[1], row[0]))
    prices = [price for _, price in rows]
    result = {
        "trading_date": target, "adjclose": prices[-1], "window_samples": len(window),
        "highest_adjclose": highest, "highest_date": highest_date,
        "drawdown": prices[-1] / highest - 1, "rsi14": wilder_rsi(prices),
        "sma50": sma(prices, 50), "sma200": sma(prices, 200),
        "rsi_warmup_prices": len(prices), "high_tie_rule": "LATEST_DATE_EXACT_EQUAL_PRICE",
    }
    result["indicator_status"] = {key: "VALID" if result[key] is not None else "INSUFFICIENT_HISTORY"
                                  for key in ("drawdown", "rsi14", "sma50", "sma200")}
    return result
