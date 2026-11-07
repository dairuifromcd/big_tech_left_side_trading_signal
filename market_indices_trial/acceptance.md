# Market Indices 扩展验收

MARKET_INDICES_EXTENSION: PASS

237/237测试通过，原208项全部保留；无跳过；回归阶段真实网络请求0。

| 指数 | HTTP | 完整Adj Close记录 | 最新交易日 | Close/Adj Close | exchange |
|---|---|---|---|---|---|
| ^GSPC | 200 | 501 | 2026-11-06 | 完全相等 | SNP/SNP |
| ^NDX | 200 | 501 | 2026-11-06 | 完全相等 | NIM/Nasdaq GIDS |
| ^SOX | 200 | 501 | 2026-11-06 | 完全相等 | NIM/Nasdaq GIDS |

仅新增三指数各采集一次，串行至少5秒，不重试；未请求旧九股。SOX实际volume为501个0，缺失/null成交量的离线测试同样通过。

三个指数均为INDEX/USD/America/New_York；使用独立显式初始化的v2指数状态。首次基线无事件；重复运行字节幂等。
原387个已跟踪文件（包括346份受保护状态和历史证据）全部保持原哈希；原7条待复核决策未动。

## AVGO 2026-11-06 只读诊断

前日回撤 -39.256369%，当日 -38.806311%，改善 0.450058 个百分点。
旧deepening_anchor为 -32.859668%，累计未确认加深仍为 5.946643 个百分点，超过1.0门槛。
当日WATCH_30未退出，所以标量模型不判RECOVERY。旧锚点因前日候选未确认而保留；当日候选仍为DEEPER_DRAWDOWN，但顶层摘要和事件状态实际均为PENDING_REVIEW，不能解释成当日新增已确认下跌。
建议后续单独区分“本日增量”和“自旧锚点累计未确认加深”，保留原始候选日、事件ID与未消费的锚点。本任务未修改股票模型、未批准或拒绝任何待复核项。

## Phase5建议

Eligible as an isolated integration candidate; live index cross-day reliability, explicit index-review workflow and unattended recovery still require validation. No automatic production promotion.

## 限制

- Yahoo single source; issuer descriptions do not authenticate vendor-specific exchange codes.
- Exact two-year left boundary is not independently certified; complete internal calendar coverage is verified.
- All index price revisions are conservatively pending; this is stricter than the stock precision-comparability policy.
- Only one actual index capture; multi-session scenarios are offline fixtures.
- Bounded existing 2024–2028 calendar remains unchanged.
