# Local technical observations

Mode: FOUR_DAY_LIVE_DRY_RUN; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-11-04 | 200.1300 | 200.1300 | 252 | 239.2400 | 2026-10-06 | -16.35% | 34.5448 | 221.1514 | 204.3863 | WATCH_10 | HISTORICAL_REVISION | PASS |
| AAPL | 2026-11-04 | 349.5100 | 349.5100 | 252 | 349.5100 | 2026-11-04 | 0.00% | 57.7819 | 334.8436 | 297.5760 | NONE | HISTORICAL_REVISION | PASS |
| GOOGL | 2026-11-04 | 288.9300 | 288.9300 | 252 | 402.1212 | 2026-05-13 | -28.15% | 30.2161 | 335.2034 | 339.6679 | WATCH_20 | RECOVERY | PASS |
| MSFT | 2026-11-04 | 555.8000 | 555.8000 | 252 | 555.8000 | 2026-11-04 | 0.00% | 64.3312 | 515.3436 | 437.9615 | NONE | HISTORICAL_REVISION | PASS |
| AMZN | 2026-11-04 | 266.0300 | 266.0300 | 252 | 284.0200 | 2026-08-03 | -6.33% | 59.8733 | 253.8908 | 243.6709 | NONE | RECOVERY | PASS |
| SPCX | 2026-11-04 | 135.9200 | 135.9200 | 101 | 211.3900 | 2026-06-16 | -35.70% | 40.0927 | 149.6350 | N/A | WATCH_30 | NO_CHANGE | PASS_PROVISIONAL |
| META | 2026-11-04 | 630.0000 | 630.0000 | 252 | 777.5900 | 2026-09-24 | -18.98% | 40.1334 | 673.3910 | 631.3620 | WATCH_10 | RECOVERY | PASS |
| AVGO | 2026-11-04 | 325.4800 | 325.4800 | 252 | 479.9351 | 2026-06-02 | -32.18% | 42.0628 | 350.5022 | 366.4286 | WATCH_30 | HISTORICAL_REVISION | PASS |
| TSLA | 2026-11-04 | 385.1900 | 385.1900 | 252 | 489.8800 | 2025-12-16 | -21.37% | 51.3755 | 372.1116 | 384.7595 | WATCH_20 | NEW_THRESHOLD | PASS |

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
