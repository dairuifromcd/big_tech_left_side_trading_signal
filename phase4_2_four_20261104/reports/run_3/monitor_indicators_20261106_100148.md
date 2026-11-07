# Local technical observations

Mode: FOUR_DAY_LIVE_DRY_RUN; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-11-05 | 181.6000 | 181.6000 | 252 | 239.2400 | 2026-10-06 | -24.09% | 25.3952 | 220.5949 | 204.3798 | WATCH_20 | NEW_THRESHOLD | PASS |
| AAPL | 2026-11-05 | 344.1700 | 344.1700 | 252 | 349.5100 | 2026-11-04 | -1.53% | 53.0079 | 335.4580 | 298.0619 | NONE | HISTORICAL_REVISION | PASS |
| GOOGL | 2026-11-05 | 282.5700 | 282.5700 | 252 | 402.1212 | 2026-05-13 | -29.73% | 27.9871 | 334.0192 | 339.4420 | WATCH_20 | DEEPER_DRAWDOWN | PASS |
| MSFT | 2026-11-05 | 535.9300 | 535.9300 | 252 | 555.8000 | 2026-11-04 | -3.58% | 54.4559 | 516.1348 | 438.4346 | NONE | HISTORICAL_REVISION | PASS |
| AMZN | 2026-11-05 | 260.2100 | 260.2100 | 252 | 284.0200 | 2026-08-03 | -8.38% | 54.9692 | 253.8894 | 243.8154 | NONE | NO_CHANGE | PASS |
| SPCX | 2026-11-05 | 123.6200 | 123.6200 | 102 | 211.3900 | 2026-06-16 | -41.52% | 32.8941 | 149.3148 | N/A | WATCH_30 | PENDING_REVIEW | PASS_PROVISIONAL |
| META | 2026-11-05 | 605.0800 | 605.0800 | 252 | 777.5900 | 2026-09-24 | -22.19% | 34.9500 | 673.9789 | 631.3304 | WATCH_20 | REENTRY | PASS |
| AVGO | 2026-11-05 | 291.5300 | 291.5300 | 252 | 479.9351 | 2026-06-02 | -39.26% | 31.4766 | 349.2339 | 366.2512 | WATCH_30 | PENDING_REVIEW | PASS |
| TSLA | 2026-11-05 | 343.6900 | 343.6900 | 252 | 489.8800 | 2025-12-16 | -29.84% | 35.8093 | 372.0690 | 384.3208 | WATCH_20 | DEEPER_DRAWDOWN | PASS |

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
