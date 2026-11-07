# Local technical observations

Mode: LIVE_FETCH; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-11-02 | 202.0600 | 202.0600 | 252 | 239.2400 | 2026-10-06 | -15.54% | 33.3141 | 221.4362 | 204.1694 | WATCH_10 | FIRST_BASELINE | PASS |
| AAPL | 2026-11-02 | 338.3200 | 338.3200 | 252 | 348.9100 | 2026-10-29 | -3.04% | 47.8766 | 333.6202 | 296.6733 | NONE | FIRST_BASELINE | PASS |
| GOOGL | 2026-11-02 | 278.9900 | 278.9900 | 252 | 402.1212 | 2026-05-13 | -30.62% | 21.1733 | 337.7157 | 340.0768 | WATCH_30 | FIRST_BASELINE | PASS |
| MSFT | 2026-11-02 | 507.1200 | 507.1200 | 252 | 543.4500 | 2026-10-13 | -6.69% | 40.1377 | 513.3882 | 437.1206 | NONE | FIRST_BASELINE | PASS |
| AMZN | 2026-11-02 | 245.6300 | 245.6300 | 252 | 284.0200 | 2026-08-03 | -13.52% | 43.8602 | 254.0190 | 243.4379 | WATCH_10 | FIRST_BASELINE | PASS |
| SPCX | 2026-11-02 | 136.3700 | 136.3700 | 99 | 211.3900 | 2026-06-16 | -35.49% | 38.9314 | 149.5494 | N/A | WATCH_30 | FIRST_BASELINE | PASS_PROVISIONAL |
| META | 2026-11-02 | 606.7300 | 606.7300 | 252 | 777.5900 | 2026-09-24 | -21.97% | 31.7407 | 670.9340 | 631.2130 | WATCH_20 | FIRST_BASELINE | PASS |
| AVGO | 2026-11-02 | 322.2300 | 322.2300 | 252 | 479.9351 | 2026-06-02 | -32.86% | 39.3397 | 351.6339 | 366.5433 | WATCH_30 | FIRST_BASELINE | PASS |
| TSLA | 2026-11-02 | 403.8200 | 403.8200 | 252 | 489.8800 | 2025-12-16 | -17.57% | 62.4632 | 370.4218 | 385.1248 | WATCH_10 | FIRST_BASELINE | PASS |

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
