# Local technical observations

Mode: LIVE_FETCH; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-10-29 | 213.6600 | 213.6600 | 252 | 239.2400 | 2026-10-06 | -10.69% | 42.2847 | 221.9240 | 203.9825 | WATCH_10 | HISTORICAL_REVISION | PASS |
| AAPL | 2026-10-29 | 348.9100 | 348.9100 | 252 | 348.9100 | 2026-10-29 | 0.00% | 61.3915 | 332.3742 | 295.8423 | NONE | HISTORICAL_REVISION | PASS |
| GOOGL | 2026-10-29 | 283.8200 | 283.8200 | 252 | 402.1212 | 2026-05-13 | -29.42% | 22.3225 | 340.2400 | 340.6192 | WATCH_20 | HISTORICAL_REVISION | PASS |
| MSFT | 2026-10-29 | 530.1400 | 530.1400 | 252 | 543.4500 | 2026-10-13 | -2.45% | 55.3700 | 512.0954 | 436.5268 | NONE | HISTORICAL_REVISION | PASS |
| AMZN | 2026-10-29 | 243.7900 | 243.7900 | 252 | 284.0200 | 2026-08-03 | -14.16% | 40.7189 | 254.6742 | 243.3821 | WATCH_10 | NO_CHANGE | PASS |
| SPCX | 2026-10-29 | 143.8900 | 143.8900 | 97 | 211.3900 | 2026-06-16 | -31.93% | 43.6926 | 149.5470 | N/A | WATCH_30 | NO_CHANGE | PASS_PROVISIONAL |
| META | 2026-10-29 | 624.5200 | 624.5200 | 252 | 777.5900 | 2026-09-24 | -19.69% | 34.9936 | 668.3969 | 631.2701 | WATCH_10 | HISTORICAL_REVISION | PASS |
| AVGO | 2026-10-29 | 345.0000 | 345.0000 | 252 | 479.9351 | 2026-06-02 | -28.12% | 49.1049 | 353.2907 | 366.6976 | WATCH_20 | HISTORICAL_REVISION | PASS |
| TSLA | 2026-10-29 | 403.3000 | 403.3000 | 252 | 489.8800 | 2025-12-16 | -17.67% | 63.0347 | 368.5090 | 385.4955 | WATCH_10 | NO_CHANGE | PASS |

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
