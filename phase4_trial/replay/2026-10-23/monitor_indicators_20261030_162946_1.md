# Local technical observations

Mode: OFFLINE_REPLAY; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-10-23 | 210.9600 | 210.9600 | 252 | 239.2400 | 2026-10-06 | -11.82% | 38.1063 | 222.3939 | 203.3622 | WATCH_10 | NO_CHANGE | PASS |
| AAPL | 2026-10-23 | 347.7300 | 347.7300 | 252 | 348.2200 | 2026-10-22 | -0.14% | 63.9280 | 329.4668 | 294.1080 | NONE | NO_CHANGE | PASS |
| GOOGL | 2026-10-23 | 320.2100 | 320.2100 | 252 | 402.1212 | 2026-05-13 | -20.37% | 31.3016 | 342.8769 | 340.9851 | WATCH_20 | NO_CHANGE | PASS |
| MSFT | 2026-10-23 | 524.5100 | 524.5100 | 252 | 543.4500 | 2026-10-13 | -3.49% | 52.6311 | 508.3546 | 435.3676 | NONE | NO_CHANGE | PASS |
| AMZN | 2026-10-23 | 248.0000 | 248.0000 | 252 | 284.0200 | 2026-08-03 | -12.68% | 43.1691 | 255.6476 | 243.2929 | WATCH_10 | NO_CHANGE | PASS |
| SPCX | 2026-10-23 | 147.4900 | 147.4900 | 93 | 211.3900 | 2026-06-16 | -30.23% | 46.3723 | 149.2394 | N/A | WATCH_30 | NO_CHANGE | PASS_PROVISIONAL |
| META | 2026-10-23 | 642.6200 | 642.6200 | 252 | 777.5900 | 2026-09-24 | -17.36% | 35.7569 | 663.5767 | 631.6592 | WATCH_10 | NO_CHANGE | PASS |
| AVGO | 2026-10-23 | 321.6800 | 321.6800 | 252 | 479.9351 | 2026-06-02 | -32.97% | 34.2595 | 356.4270 | 366.7395 | WATCH_30 | NO_CHANGE | PASS |
| TSLA | 2026-10-23 | 372.2200 | 372.2200 | 252 | 489.8800 | 2025-12-16 | -24.02% | 51.5213 | 363.7682 | 386.3474 | WATCH_20 | NO_CHANGE | PASS |

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
