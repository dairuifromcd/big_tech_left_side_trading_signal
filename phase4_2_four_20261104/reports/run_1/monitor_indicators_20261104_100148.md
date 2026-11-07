# Local technical observations

Mode: FOUR_DAY_LIVE_DRY_RUN; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-11-03 | 206.6900 | 206.6900 | 252 | 239.2400 | 2026-10-06 | -13.61% | 39.1859 | 221.4051 | 204.2739 | WATCH_10 | HISTORICAL_REVISION | PASS |
| AAPL | 2026-11-03 | 331.9000 | 331.9000 | 252 | 348.9100 | 2026-10-29 | -4.88% | 41.7045 | 334.0514 | 297.0586 | NONE | HISTORICAL_REVISION | PASS |
| GOOGL | 2026-11-03 | 280.0300 | 280.0300 | 252 | 402.1212 | 2026-05-13 | -30.36% | 22.1606 | 336.3595 | 339.8301 | WATCH_30 | HISTORICAL_REVISION | PASS |
| MSFT | 2026-11-03 | 520.9900 | 520.9900 | 252 | 543.4500 | 2026-10-13 | -4.13% | 49.4057 | 514.0618 | 437.4408 | NONE | HISTORICAL_REVISION | PASS |
| AMZN | 2026-11-03 | 250.6900 | 250.6900 | 252 | 284.0200 | 2026-08-03 | -11.74% | 48.6638 | 253.7914 | 243.4957 | WATCH_10 | NO_CHANGE | PASS |
| SPCX | 2026-11-03 | 141.3100 | 141.3100 | 100 | 211.3900 | 2026-06-16 | -33.15% | 44.0119 | 149.6756 | N/A | WATCH_30 | NO_CHANGE | PASS_PROVISIONAL |
| META | 2026-11-03 | 621.0300 | 621.0300 | 252 | 777.5900 | 2026-09-24 | -20.13% | 37.0110 | 672.1830 | 631.2248 | WATCH_20 | HISTORICAL_REVISION | PASS |
| AVGO | 2026-11-03 | 332.1300 | 332.1300 | 252 | 479.9351 | 2026-06-02 | -30.80% | 44.8035 | 351.1144 | 366.4550 | WATCH_30 | HISTORICAL_REVISION | PASS |
| TSLA | 2026-11-03 | 398.5000 | 398.5000 | 252 | 489.8800 | 2025-12-16 | -18.65% | 59.0156 | 371.4128 | 384.9298 | WATCH_10 | DEEPER_DRAWDOWN | PASS |

Warnings and errors:

- NVDA: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed
- AAPL: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed
- GOOGL: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed
- MSFT: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed
- AMZN: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed
- SPCX: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed; YAHOO_ONLY/HISTORICAL_ANOMALY_UNVERIFIED: all SPCX observations provisional; Close discrepancy cannot establish the Adj Close correction or its effect on tiers; SMA200: INSUFFICIENT_HISTORY
- META: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed
- AVGO: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed
- TSLA: YAHOO_ONLY: history is not independently price-verified; TECHNICAL_OBSERVATION_ONLY: investment value not assessed

SPCX historical conflict: user-reported 2026-06-16 Yahoo Close $211.39 vs Nasdaq Close $201.80; Close only, not an established Adj Close discrepancy. All SPCX observations are provisional.
