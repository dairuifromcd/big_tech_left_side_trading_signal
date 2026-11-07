# Local technical observations

Mode: OFFLINE_REPLAY; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-10-27 | 217.9400 | 217.9400 | 252 | 239.2400 | 2026-10-06 | -8.90% | 46.3053 | 222.0794 | 203.6868 | NONE | NO_CHANGE | PASS |
| AAPL | 2026-10-27 | 347.1000 | 347.1000 | 252 | 348.2200 | 2026-10-22 | -0.32% | 61.1067 | 331.0566 | 294.9780 | NONE | NO_CHANGE | PASS |
| GOOGL | 2026-10-27 | 320.5800 | 320.5800 | 252 | 402.1212 | 2026-05-13 | -20.28% | 33.9609 | 341.8354 | 340.9083 | WATCH_20 | NO_CHANGE | PASS |
| MSFT | 2026-10-27 | 531.3300 | 531.3300 | 252 | 543.4500 | 2026-10-13 | -2.23% | 56.3290 | 510.1549 | 435.9304 | NONE | NO_CHANGE | PASS |
| AMZN | 2026-10-27 | 253.1000 | 253.1000 | 252 | 284.0200 | 2026-08-03 | -10.89% | 48.5767 | 255.2122 | 243.3355 | WATCH_10 | NO_CHANGE | PASS |
| SPCX | 2026-10-27 | 148.5800 | 148.5800 | 95 | 211.3900 | 2026-06-16 | -29.71% | 47.4501 | 149.4244 | N/A | WATCH_20 | RECOVERY | PASS_PROVISIONAL |
| META | 2026-10-27 | 620.1900 | 620.1900 | 252 | 777.5900 | 2026-09-24 | -20.24% | 31.9449 | 665.4335 | 631.4340 | WATCH_20 | NEW_THRESHOLD | PASS |
| AVGO | 2026-10-27 | 342.3300 | 342.3300 | 252 | 479.9351 | 2026-06-02 | -28.67% | 47.7596 | 354.1771 | 366.7283 | WATCH_20 | RECOVERY | PASS |
| TSLA | 2026-10-27 | 407.4600 | 407.4600 | 252 | 489.8800 | 2025-12-16 | -16.82% | 65.4768 | 366.1184 | 385.9387 | WATCH_10 | RECOVERY | PASS |

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
