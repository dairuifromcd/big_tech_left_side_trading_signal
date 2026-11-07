# Local technical observations

Mode: OFFLINE_REPLAY; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-10-28 | 215.3800 | 215.3800 | 252 | 239.2400 | 2026-10-06 | -9.97% | 43.8843 | 221.9971 | 203.8411 | NONE | NO_CHANGE | PASS |
| AAPL | 2026-10-28 | 343.8300 | 343.8300 | 252 | 348.2200 | 2026-10-22 | -1.26% | 56.1152 | 331.7326 | 295.3995 | NONE | NO_CHANGE | PASS |
| GOOGL | 2026-10-28 | 324.8900 | 324.8900 | 252 | 402.1212 | 2026-05-13 | -19.21% | 38.6753 | 341.4536 | 340.8767 | WATCH_10 | NO_CHANGE | PASS |
| MSFT | 2026-10-28 | 531.0100 | 531.0100 | 252 | 543.4500 | 2026-10-13 | -2.29% | 56.0817 | 511.1606 | 436.2146 | NONE | NO_CHANGE | PASS |
| AMZN | 2026-10-28 | 254.6000 | 254.6000 | 252 | 284.0200 | 2026-08-03 | -10.36% | 50.1039 | 255.1152 | 243.3761 | WATCH_10 | NO_CHANGE | PASS |
| SPCX | 2026-10-28 | 145.2300 | 145.2300 | 96 | 211.3900 | 2026-06-16 | -31.30% | 44.7597 | 149.4622 | N/A | WATCH_30 | NO_CHANGE | PASS_PROVISIONAL |
| META | 2026-10-28 | 612.4900 | 612.4900 | 252 | 777.5900 | 2026-09-24 | -21.23% | 30.6871 | 666.8185 | 631.2948 | WATCH_20 | NO_CHANGE | PASS |
| AVGO | 2026-10-28 | 351.8100 | 351.8100 | 252 | 479.9351 | 2026-06-02 | -26.70% | 52.6905 | 353.6271 | 366.7359 | WATCH_20 | NO_CHANGE | PASS |
| TSLA | 2026-10-28 | 404.2200 | 404.2200 | 252 | 489.8800 | 2025-12-16 | -17.49% | 63.5901 | 367.4654 | 385.7150 | WATCH_10 | NO_CHANGE | PASS |

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
