# Local technical observations

Mode: OFFLINE_SNAPSHOT; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-11-06 | 186.6400 | 186.6400 | 252 | 239.2400 | 2026-10-06 | -21.99% | 30.7664 | 219.7732 | 204.3910 | WATCH_20 | NO_CHANGE | PASS |
| AAPL | 2026-11-06 | 342.3700 | 342.3700 | 252 | 349.5100 | 2026-11-04 | -2.04% | 51.4643 | 336.0138 | 298.5354 | NONE | NO_CHANGE | PASS |
| GOOGL | 2026-11-06 | 284.7800 | 284.7800 | 252 | 402.1212 | 2026-05-13 | -29.18% | 29.9216 | 332.9062 | 339.2164 | WATCH_20 | NO_CHANGE | PASS |
| MSFT | 2026-11-06 | 530.6100 | 530.6100 | 252 | 555.8000 | 2026-11-04 | -4.53% | 52.1477 | 516.6458 | 438.8462 | NONE | NO_CHANGE | PASS |
| AMZN | 2026-11-06 | 259.3000 | 259.3000 | 252 | 284.0200 | 2026-08-03 | -8.70% | 54.2213 | 253.9502 | 243.9401 | NONE | NO_CHANGE | PASS |
| SPCX | 2026-11-06 | 134.2700 | 134.2700 | 103 | 211.3900 | 2026-06-16 | -36.48% | 42.5179 | 149.1828 | N/A | WATCH_30 | NO_CHANGE | PASS_PROVISIONAL |
| META | 2026-11-06 | 610.1500 | 610.1500 | 252 | 777.5900 | 2026-09-24 | -21.53% | 36.7401 | 674.7689 | 631.1514 | WATCH_20 | NO_CHANGE | PASS |
| AVGO | 2026-11-06 | 293.6900 | 293.6900 | 252 | 479.9351 | 2026-06-02 | -38.81% | 32.6382 | 347.6904 | 366.1011 | WATCH_30 | NO_CHANGE | PASS |
| TSLA | 2026-11-06 | 358.2200 | 358.2200 | 252 | 489.8800 | 2025-12-16 | -26.88% | 42.3907 | 372.1372 | 383.8651 | WATCH_20 | NO_CHANGE | PASS |

Daily movement and cumulative unconfirmed anchor scope:

| Symbol | Daily drawdown change (pp) | New deepening today | Cumulative anchor depth (pp) | Raw candidate | Status | Confirmed |
|---|---:|---|---:|---|---|---|
| NVDA | 0.0 | False | -2.106668270527534 | NO_CHANGE | NO_EVENT | False |
| AAPL | 0.0 | False | -0.9923014423859677 | NO_CHANGE | NO_EVENT | False |
| GOOGL | 0.0 | False | -0.5495834429649182 | NO_CHANGE | NO_EVENT | False |
| MSFT | 0.0 | False | -2.1528642498147232 | NO_CHANGE | NO_EVENT | False |
| AMZN | 0.0 | False | 2.3695553998504537 | NO_CHANGE | NO_EVENT | False |
| SPCX | 0.0 | False | 0.9934201479681715 | NO_CHANGE | NO_EVENT | False |
| META | 0.0 | False | -0.652015477194523 | NO_CHANGE | NO_EVENT | False |
| AVGO | 0.0 | False | 5.94664317472593 | NO_CHANGE | NO_EVENT | False |
| TSLA | 0.0 | False | -2.96603221900692 | NO_CHANGE | NO_EVENT | False |

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
