# Phase 4.2 四次有限期试运行总结

状态：COMPLETED；结果：PASS_PROVISIONAL；最终总结：True。

仅真实日志计为完成；2026-11-03人工采集是继承基线，不计入四次自动运行。

| Run | Brisbane 执行时间 | 目标美股交易日 | HTTP次数 | 状态更新 | 结果 |
|---|---|---|---|---|---|
| 1 | 2026-11-04T10:00:00+10:00 | 2026-11-03 | 9 | True | SUCCESS |
| 2 | 2026-11-05T10:00:00+10:00 | 2026-11-04 | 9 | True | SUCCESS |
| 3 | 2026-11-06T10:00:00+10:00 | 2026-11-05 | 9 | True | SUCCESS |
| 4 | 2026-11-07T10:00:00+10:00 | 2026-11-06 | 9 | True | SUCCESS |

基线交易日：2026-11-02；基线来源：/Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal/phase4_2_manual_20261103/state/monitor_state.json。

最多四次认领，失败计数；不重试、不自动补跑；严重异常提前停止全部本次调度。
Mac须开机、登录、联网并在10:00保持唤醒。迟到超过15分钟拒绝采集；关机期间不能清理，恢复后拒绝过期采集并清理。
周六第4次结束后生成最终总结并清理；10:30仅清理和汇总的任务不请求Yahoo。
SPCX为PASS_PROVISIONAL，历史异常未独立核实；未观测到真实触档时不声称已发生。

## Run 1

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


状态哈希：48aca297e54965b1169487be61969b152591f424c19ea3d8e22fdabbb67724ee → a965e461e05fdaa800f7fc08e2d5585434cb2d3b0df6b01306a99e72c4f5a451。

## Run 2

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


状态哈希：a965e461e05fdaa800f7fc08e2d5585434cb2d3b0df6b01306a99e72c4f5a451 → bbd5624801ac7146868ba02820ad49d3355599e4176eb81a598af10da396ee34。

## Run 3

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


状态哈希：bbd5624801ac7146868ba02820ad49d3355599e4176eb81a598af10da396ee34 → fff1cd546ebcec0c19f5d3aaedfdd4f12a7d7153812b81d347a8b9dcbcadf8e6。

## Run 4

# Local technical observations

Mode: FOUR_DAY_LIVE_DRY_RUN; captured market history, not a new quote. No investment-value rating.

| Symbol | Trading Date | Close | Adj Close | Samples | High Adj | High Date | Drawdown | RSI14 | SMA50 | SMA200 | Tier | Event | Quality |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|
| NVDA | 2026-11-06 | 186.6400 | 186.6400 | 252 | 239.2400 | 2026-10-06 | -21.99% | 30.7664 | 219.7732 | 204.3910 | WATCH_20 | HISTORICAL_REVISION | PASS |
| AAPL | 2026-11-06 | 342.3700 | 342.3700 | 252 | 349.5100 | 2026-11-04 | -2.04% | 51.4643 | 336.0138 | 298.5354 | NONE | HISTORICAL_REVISION | PASS |
| GOOGL | 2026-11-06 | 284.7800 | 284.7800 | 252 | 402.1212 | 2026-05-13 | -29.18% | 29.9216 | 332.9062 | 339.2164 | WATCH_20 | HISTORICAL_REVISION | PASS |
| MSFT | 2026-11-06 | 530.6100 | 530.6100 | 252 | 555.8000 | 2026-11-04 | -4.53% | 52.1477 | 516.6458 | 438.8462 | NONE | HISTORICAL_REVISION | PASS |
| AMZN | 2026-11-06 | 259.3000 | 259.3000 | 252 | 284.0200 | 2026-08-03 | -8.70% | 54.2213 | 253.9502 | 243.9401 | NONE | NO_CHANGE | PASS |
| SPCX | 2026-11-06 | 134.2700 | 134.2700 | 103 | 211.3900 | 2026-06-16 | -36.48% | 42.5179 | 149.1828 | N/A | WATCH_30 | NO_CHANGE | PASS_PROVISIONAL |
| META | 2026-11-06 | 610.1500 | 610.1500 | 252 | 777.5900 | 2026-09-24 | -21.53% | 36.7401 | 674.7689 | 631.1514 | WATCH_20 | HISTORICAL_REVISION | PASS |
| AVGO | 2026-11-06 | 293.6900 | 293.6900 | 252 | 479.9351 | 2026-06-02 | -38.81% | 32.6382 | 347.6904 | 366.1011 | WATCH_30 | PENDING_REVIEW | PASS |
| TSLA | 2026-11-06 | 358.2200 | 358.2200 | 252 | 489.8800 | 2025-12-16 | -26.88% | 42.3907 | 372.1372 | 383.8651 | WATCH_20 | NO_CHANGE | PASS |

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


状态哈希：fff1cd546ebcec0c19f5d3aaedfdd4f12a7d7153812b81d347a8b9dcbcadf8e6 → 9b60dc77cf8e25a7487910fb3dedb73e6fe37ebe225a40e959ae23f657b93c4e。

