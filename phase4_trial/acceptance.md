# Phase 4 本地可靠性验收

DRY_RUN；真实采集仅一轮。正式 Phase 3 状态保持不变。

测试85/85通过；真实HTTP200=9/9；429=0；总耗时102.119秒。

| 股票 | Adj Close | 回撤 | RSI14 | SMA50 | SMA200 | 档位 | 事件 |
|---|---:|---:|---:|---:|---:|---|---|
| NVDA | 213.66 | -10.69% | 42.28 | 221.92 | 203.98 | WATCH_10 | HISTORICAL_REVISION |
| AAPL | 348.91 | 0.00% | 61.39 | 332.37 | 295.84 | NONE | HISTORICAL_REVISION |
| GOOGL | 283.82 | -29.42% | 22.32 | 340.24 | 340.62 | WATCH_20 | HISTORICAL_REVISION |
| MSFT | 530.14 | -2.45% | 55.37 | 512.10 | 436.53 | NONE | HISTORICAL_REVISION |
| AMZN | 243.79 | -14.16% | 40.72 | 254.67 | 243.38 | WATCH_10 | NO_CHANGE |
| SPCX | 143.89 | -31.93% | 43.69 | 149.55 | N/A | WATCH_30 | NO_CHANGE |
| META | 624.52 | -19.69% | 34.99 | 668.40 | 631.27 | WATCH_10 | HISTORICAL_REVISION |
| AVGO | 345.00 | -28.12% | 49.10 | 353.29 | 366.70 | WATCH_20 | HISTORICAL_REVISION |
| TSLA | 403.30 | -17.67% | 63.03 | 368.51 | 385.50 | WATCH_10 | NO_CHANGE |

全部目标交易日2026-10-29；SPCX为PASS_PROVISIONAL。6股历史价格差异按HISTORICAL_REVISION记录，不推断修订原因，无新增真实下跌触档。

五日回放：2026-10-23, 2026-10-26, 2026-10-27, 2026-10-28, 2026-10-29；12条历史观察事件；逐日重复全部幂等。它们不是实时新发现。

验收：
- END_TO_END_EXECUTION: PASS
- LIVE_DATA_VALIDATION: PASS
- STATE_RECOVERY: PASS
- FAILURE_HANDLING: PASS
- IDEMPOTENCY: PASS
- CROSS_DAY_LIVE_VALIDATION: PENDING_LIVE_VALIDATION

正式状态SHA256：`26e0f3f84e579b448e6e57fad9abd8b550568520c0088c0ff106f34eae727fa6`

限制：
- Yahoo single source; SPCX provisional and disputed high unresolved
- Historical replay truncates a captured adjusted-price snapshot; does not reconstruct historical point-in-time revision vintages
- Real separate-trading-day executions have not occurred
- Calendar2024–2028 and emergency closures require maintenance
- Local backup/fsync cannot guarantee hardware durability; explicitly selected recovery can roll back consumed events
