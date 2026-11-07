# Yahoo 历史 Adj Close 修订补充诊断

本次完全离线，新增 HTTP 请求为 0。未修改生产代码、正式容差、任何状态或既有证据。

按纽约交易日期匹配 4105 对价格；当前容差复现 **1139** 条修订；普通 Close 差异 **0**。

## 证据与口径

已从 Phase 4 acceptance.live_report 定位真实采集报告，再从 input_file/collection_report 定位行情及校验摘要。两份行情 SHA256、正式状态已记录 SHA256 均匹配；其他无既存哈希的报告只记录当前清单摘要，不伪称已通过历史签名验证。
价格按 symbol + America/New_York 交易日匹配，重跑既有证券身份、时间戳、完整交易时段、交易日历与价格校验。所有原始行均已完成，日期相同且无缺失/重复；夏令时偏移包含 -04:00/-05:00，两轮时间戳逐日一致。
当前生产代码组合SHA256与Phase4采集时记录一致。每股raw response_sha256无法从规范化证据重新验证：原始HTTP字节未保存；不得将价格证据文件哈希匹配冒充原始响应或独立价格真实性验证。
当前生产比较：math.isclose(abs_tol=1e-8, rel_tol=1e-10)。相对差分母是 Phase 2 价格。P95 使用(n-1)×0.95线性插值。

## 九股差异汇总

| Symbol | Overlap | Revisions | Max Abs Diff ($) | Max Rel Diff | Likely Cause |
|---|---:|---:|---:|---:|---|
| NVDA | 501 | 210 | 4.57763671875e-05 | 3.30639212e-07 | NUMERIC_PRECISION（可能，上游未确认） |
| AAPL | 501 | 204 | 6.103515625e-05 | 2.38102551e-07 | NUMERIC_PRECISION（可能，上游未确认） |
| GOOGL | 501 | 189 | 6.103515625e-05 | 2.64702504e-07 | NUMERIC_PRECISION（可能，上游未确认） |
| MSFT | 501 | 162 | 0.0001220703125 | 2.3762796e-07 | NUMERIC_PRECISION（可能，上游未确认） |
| AMZN | 501 | 0 | 0 | 0 | 无观察到差异；原因不适用 |
| SPCX | 97 | 0 | 0 | 0 | 无观察到差异；原因不适用 |
| META | 501 | 156 | 0.00018310546875 | 3.2379533e-07 | NUMERIC_PRECISION（可能，上游未确认） |
| AVGO | 501 | 218 | 9.1552734375e-05 | 3.18393666e-07 | NUMERIC_PRECISION（可能，上游未确认） |
| TSLA | 501 | 0 | 0 | 0 | 无观察到差异；原因不适用 |

绝对差分组（包含相等价格对；不是新容差）：

- le_0.000001: 2966
- gt_0.000001_le_0.0001: 1122
- gt_0.0001_le_0.01: 17
- gt_0.01_le_0.10: 0
- gt_0.10: 0

| Symbol | 中位数：全部 | P95：全部 | 中位数：变化对 | P95：变化对 | 最早变化日 | 最晚变化日 |
|---|---:|---:|---:|---:|---|---|
| NVDA | 0 | 3.0517578125e-05 | 1.52587890625e-05 | 3.0517578125e-05 | 2024-10-30 | 2026-05-28 |
| AAPL | 0 | 3.0517578125e-05 | 1.52587890625e-05 | 3.0517578125e-05 | 2024-10-30 | 2026-05-07 |
| GOOGL | 0 | 3.0517578125e-05 | 1.52587890625e-05 | 3.0517578125e-05 | 2024-10-31 | 2026-03-05 |
| MSFT | 0 | 6.103515625e-05 | 3.0517578125e-05 | 6.103515625e-05 | 2024-10-31 | 2026-05-14 |
| AMZN | 0 | 0 | N/A | N/A | N/A | N/A |
| SPCX | 0 | 0 | N/A | N/A | N/A | N/A |
| META | 0 | 6.103515625e-05 | 6.103515625e-05 | 0.0001220703125 | 2024-10-31 | 2026-03-11 |
| AVGO | 0 | 3.0517578125e-05 | 3.0517578125e-05 | 4.80651855469e-05 | 2024-10-31 | 2026-06-16 |
| TSLA | 0 | 0 | N/A | N/A | N/A | N/A |

每股最大差异前5日（全部逐日差异另存独立 JSON，含两次价格及复权比率）：

| Symbol | Date | Phase 2 Adj | Phase 4 Adj | Abs Diff | Relative Diff |
|---|---|---:|---:|---:|---:|
| NVDA | 2024-12-09 | 138.44808959960938 | 138.44804382324219 | 4.57763671875e-05 | 3.30639211562e-07 |
| NVDA | 2025-06-05 | 139.6378173828125 | 139.63786315917969 | 4.57763671875e-05 | 3.27822133327e-07 |
| NVDA | 2024-10-30 | 138.96711730957031 | 138.96708679199219 | 3.0517578125e-05 | 2.19602872362e-07 |
| NVDA | 2024-11-06 | 145.2203369140625 | 145.22030639648438 | 3.0517578125e-05 | 2.10146724443e-07 |
| NVDA | 2024-11-08 | 147.23490905761719 | 147.23493957519531 | 3.0517578125e-05 | 2.07271348353e-07 |
| AAPL | 2024-12-24 | 256.33978271484375 | 256.3397216796875 | 6.103515625e-05 | 2.38102551245e-07 |
| AAPL | 2026-02-06 | 277.364990234375 | 277.36505126953125 | 6.103515625e-05 | 2.20053569841e-07 |
| AAPL | 2024-11-01 | 221.06077575683594 | 221.06082153320312 | 4.57763671875e-05 | 2.0707593661e-07 |
| AAPL | 2024-12-27 | 253.74856567382812 | 253.74851989746094 | 4.57763671875e-05 | 1.80400496318e-07 |
| AAPL | 2025-01-10 | 235.14358520507812 | 235.14353942871094 | 4.57763671875e-05 | 1.94674105813e-07 |
| GOOGL | 2025-11-26 | 319.12005615234375 | 319.1201171875 | 6.103515625e-05 | 1.91260796911e-07 |
| GOOGL | 2025-01-17 | 194.85633850097656 | 194.85629272460938 | 4.57763671875e-05 | 2.34923675256e-07 |
| GOOGL | 2025-06-26 | 172.93515014648438 | 172.93519592285156 | 4.57763671875e-05 | 2.64702503503e-07 |
| GOOGL | 2024-11-21 | 166.46107482910156 | 166.46110534667969 | 3.0517578125e-05 | 1.83331617655e-07 |
| GOOGL | 2024-11-22 | 163.61109924316406 | 163.61112976074219 | 3.0517578125e-05 | 1.86525109031e-07 |
| MSFT | 2025-09-19 | 513.7034912109375 | 513.703369140625 | 0.0001220703125 | 2.37627959686e-07 |
| MSFT | 2025-10-24 | 519.33697509765625 | 519.33709716796875 | 0.0001220703125 | 2.35050301352e-07 |
| MSFT | 2025-09-29 | 510.40048217773438 | 510.40057373046875 | 9.1552734375e-05 | 1.79374310119e-07 |
| MSFT | 2024-11-06 | 413.64566040039062 | 413.64559936523438 | 6.103515625e-05 | 1.47554204221e-07 |
| MSFT | 2024-11-07 | 418.81402587890625 | 418.81396484375 | 6.103515625e-05 | 1.45733314738e-07 |
| META | 2024-11-27 | 565.49755859375 | 565.49774169921875 | 0.00018310546875 | 3.23795330267e-07 |
| META | 2024-11-29 | 570.58441162109375 | 570.584228515625 | 0.00018310546875 | 3.20908642123e-07 |
| META | 2024-10-31 | 563.88824462890625 | 563.88812255859375 | 0.0001220703125 | 2.16479619256e-07 |
| META | 2024-11-13 | 576.227294921875 | 576.2274169921875 | 0.0001220703125 | 2.11844030256e-07 |
| META | 2024-12-02 | 588.973876953125 | 588.9739990234375 | 0.0001220703125 | 2.07259298378e-07 |
| AVGO | 2025-07-25 | 287.54571533203125 | 287.54562377929688 | 9.1552734375e-05 | 3.18393665749e-07 |
| AVGO | 2025-07-14 | 273.0980224609375 | 273.09808349609375 | 6.103515625e-05 | 2.23491754719e-07 |
| AVGO | 2025-08-11 | 301.14114379882812 | 301.14108276367188 | 6.103515625e-05 | 2.02679565735e-07 |
| AVGO | 2025-08-14 | 308.40457153320312 | 308.40463256835938 | 6.103515625e-05 | 1.97906133319e-07 |
| AVGO | 2025-09-05 | 331.84979248046875 | 331.849853515625 | 6.103515625e-05 | 1.83924045255e-07 |

## 原因诊断

六只有差异的股票均存在非1复权比率；三只无差异股票全程 Adj Close/Close=1。全部两轮价格均可被 Float32 精确表示，变化为正负混合的1–3个 Float32 ULP。源 JSON 十进制数值也确实不同，因此不能解释为 Python Float64 或 JSON 解析凭空产生了价格差。
这些特征强烈符合复权处理链路中的数值舍入/计算精度变化；不是已证实的 Yahoo 内部实现原因。复权比率的数学值随 Adj Close 略变，但未观察到一致的大幅乘法调整。月度分段、ULP分布、方向及比率范围保留在 JSON；不能仅凭比例变化认定发生某次股息或拆股。
两份九股快照没有保留原始股息/拆股事件数组。较早的单股 NVDA 响应保留8个股息事件、无拆股列表，但无法证明两轮之间事件改变。整体 ROOT_CAUSE_IDENTIFIED=PARTIAL，真正上游原因仍未确认。
逐日计数实现正确：比较重叠日期的 Adj Close，不比较滚动窗口哈希，不因同日采集自动判修订，也不把单个差异扩大为整段计数。发现的问题在修订与信号事件的绑定策略。

## 指标影响（Phase 4 减 Phase 2）

| Symbol | Drawdown Δ(pp) | RSI Δ | SMA50 Δ($) | SMA200 Δ($) | High Δ($) | High Date Changed | Tier Changed |
|---|---:|---:|---:|---:|---:|---|---|
| NVDA | 0 | 9.02751651211e-10 | 0 | 0 | 0 | False | False |
| AAPL | 0 | -3.97194099833e-09 | 0 | 2.05993649161e-06 | 0 | False | False |
| GOOGL | 0 | -1.19996457215e-10 | 0 | -3.05175774429e-07 | 0 | False | False |
| MSFT | 0 | 1.69464442479e-10 | 0 | 1.52587915636e-07 | 0 | False | False |
| AMZN | 0 | 0 | 0 | 0 | 0 | False | False |
| SPCX | 0 | 0 | 0 | N/A | 0 | False | False |
| META | 0 | -9.08357833396e-11 | 0 | 3.05175717585e-07 | 0 | False | False |
| AVGO | -4.57092532713e-06 | 1.55514356948e-09 | 0 | 1.22070315456e-06 | 3.0517578125e-05 | False | False |
| TSLA | 0 | 0 | 0 | 0 | 0 | False | False |

完整两次计算值（含高点日期、窗口和最新价）在 JSON。九股的回撤变化均未达到0.01个百分点，RSI变化未达到0.01，SMA变化未达到$0.01；档位和高点日期均不变，AVGO高点数值有微小变化。这些是观察尺度，不是允许忽略差异的新规则。
当前最近档位边界仍相距 0.314818601 个百分点，未改变本批数据临近阈值的判断；边界附近的其他数据不能据此判安全。
SPCX仍为 PASS_PROVISIONAL / YAHOO_ONLY/HISTORICAL_ANOMALY_UNVERIFIED，SMA200=N/A；2026-06-16的Close冲突不构成Adj Close修正证据。

## 信号抑制风险：固定模拟 A–E

以下均为人工固定输入，不是市场事实、买点或安全通知。完整价格生成配方、旧基准及新基准结果保存在 JSON。

| 场景 | 输入/预期 | 生产实际输出 | 结论 |
|---|---|---|---|
| A | 同日最新85不变，旧低价90→90.0001；应只记录修订 | HISTORICAL_REVISION | 正确抑制虚假下跌 |
| B | 高点100不变，新交易日85→79；另有旧低价微修订，应保留真实跨-20%事实 | HISTORICAL_REVISION，跨档/新档为空 | SIGNAL_SUPPRESSION_RISK；20档却被记为已触达 |
| C | 最新85不变，高点100→110，修订造成跨档 | HISTORICAL_REVISION | 不应称为市场新下跌 |
| D | 新交易日85→81，高点100→110 | HISTORICAL_REVISION | 旧基准-19% vs 新基准-26.36%；需要复核，不能简单归因 |
| E | B被接受后，同日同数据重复运行 | NO_CHANGE，修订0，不需写状态 | 幂等正确，但不会补回B已漏掉的事件 |

B说明无条件修订覆盖会漏掉独立的新交易日跨档，且触达状态被提前消耗。D的市场/修订分解只在新旧价格单位可比的模拟假设下成立；真实复权变化可能无法可靠分解，应进入待复核而非直接通知。

## 候选容差对比（未应用）

| Policy | abs_tol | rel_tol | Revision Count | Max Ignored Abs Diff ($) |
|---|---:|---:|---:|---:|
| STRICT_EQUAL | 0 | 0 | 1139 | 0 |
| CURRENT | 1e-08 | 1e-10 | 1139 | 0 |
| ABS_1E6 | 1e-06 | 0 | 1139 | 0 |
| ABS_1E6_REL_1E7 | 1e-06 | 1e-07 | 340 | 6.103515625e-05 |
| ABS_1E4 | 0.0001 | 0 | 17 | 9.1552734375e-05 |
| ABS_1E4_REL_1E7 | 0.0001 | 1e-07 | 17 | 9.1552734375e-05 |
| ABS_1E3_REL_1E6_STRESS | 0.001 | 1e-06 | 0 | 0.00018310546875 |

比较容差仅影响修订判定和后续事件抑制，不改变实际指标输入或其数值。即使某组消除全部差异，也不能证明它安全；合成边界反例用极小高点修订造成WATCH_10→WATCH_20，详见JSON。不得以消除1,139条计数作为调参目标。

## 建议补丁方案（仅建议，未实施）

1. Separate revision facts from market-change facts; retain both in one observation rather than one unconditional event override.
2. Recompute old-basis and revised-basis windows including normal window expiration. Only compare market effects when the price units are demonstrably comparable; otherwise require manual review.
3. Split observed/candidate/pending-review/confirmed thresholds so a suppressed observation does not silently consume first-trigger eligibility.
4. Keep stable event IDs for revisions and market observations separately; preserve idempotency and suppress pure high-revision false market events.
5. Classify numeric precision versus material effects diagnostically; calibrate any tolerance using boundary and corporate-action controls, never just erase all1,139 differences.

优先修复修订事实和市场事件的无条件绑定；当前容差保留，待补丁与边界、复权单位、待复核记账测试充分后再评估候选容差。不得将历史回放/人工模拟当作安全可通知买点。

## 验收

- REVISION_COUNT_REPRODUCED: PASS
- ROOT_CAUSE_IDENTIFIED: PARTIAL
- INDICATOR_IMPACT_ASSESSED: PASS
- SIGNAL_SUPPRESSION_RISK: YES
- PRODUCTION_LOGIC_CHANGE_REQUIRED: YES

自动化测试：103项，失败0，错误0；新诊断测试18项。测试进程禁止网络访问。

## 证据清单

| File | SHA256 | Recorded Hash Check |
|---|---|---|
| yahoo_nine_prices_20261030_141537.json | 8e6796aad1dc28affe5cd6259a2cb20a367a7cc4cf8db8091db1512c03ad5e19 | MATCH |
| yahoo_nine_diagnostic_20261030_141537.json | 0c6e9aca9a2edab449a8b99cffb41f880148f9976a452605ceb13ae90d7d97b3 | NOT_RECORDED; current digest is inventory only |
| monitor_state.json | 26e0f3f84e579b448e6e57fad9abd8b550568520c0088c0ff106f34eae727fa6 | MATCH |
| acceptance.json | f6321a2baf0a35a39b25a2714eb49fe52975b7477cc6bd49187e57a70b78976a | NOT_RECORDED; current digest is inventory only |
| phase4_e2e_20261030_162933_473474.json | 06b9b9d54d745a30cabc9e2b784d3e7d3d5a9427e12f66a5f89fd4a86ad426db | NOT_RECORDED; current digest is inventory only |
| yahoo_nine_prices_20261030_162751.json | eabe9c1a4513956329b74f85eeb7b571a798069f178e653434d151c03ed18ea9 | MATCH |
| yahoo_nine_diagnostic_20261030_162751.json | f86d6e9842510ea30f05dd67a643ae67c57f05a4f06b98033e35dbd8d8bc41b6 | NOT_RECORDED; current digest is inventory only |
| monitor_indicators_20261030_162933.json | c5d499a4f70f371ab3133eb4e847e07c60445566c829d5167164115319c7198d | NOT_RECORDED; current digest is inventory only |
| phase3_execution_verification.json | ee96c717c7a028f70711903899b6e854f638b7cc31e5f89f864364c3aadd0ac7 | NOT_RECORDED; current digest is inventory only |
| monitor_indicators_20261030_152105.json | 023f86d1566678a8099ba17eb56f43ab0eda73bfdcf4e793acba24ef33f160f1 | NOT_RECORDED; current digest is inventory only |
| monitor_indicators_20261030_152207.json | eeccc25075ca5eba1e44fa5789d81733afd94ca7b26e982bec4b23087527311e | NOT_RECORDED; current digest is inventory only |
| test_yahoo_nvda_result_retest.json | 5caa39788b058c4ac90534bb81bc3da1820ce6bd01d1f99fb11073b74c66f468 | NOT_RECORDED; current digest is inventory only |

本次停止于诊断；未自动修改生产逻辑、容差、状态或监控任务，未进入Phase5。
