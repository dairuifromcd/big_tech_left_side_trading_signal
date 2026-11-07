# Phase 4.1 修复及回归验收

全程离线。测试133/133通过；无跳过；正式状态及94份既有保护文件哈希不变。

## 修复结果

修订事实与市场观察同时保留；单一change_event仅作兼容摘要。v2将observed/baseline/confirmed/pending分开，triggered_thresholds仅为confirmed兼容别名。CONFIRMED不代表通知、评级或买入。
稳定事件ID不含运行时间或价格噪声；待复核升级沿用原ID，确认/拒绝/保持待复核均保留审计。修订与阈值使用不同事件身份。
单股候选状态及账本先完整验证，再合并到全局候选；锁、备份和原子提交继续保留。

## 场景验收

| 场景 | 修复后结果 |
|---|---|
| A：同日旧低价微修订 | 保留修订，不确认新阈值 |
| B：稳定Close、高点100、新价79 | 修订事实 + CONFIRMED WATCH_20 同时存在 |
| B：旧Close也变化，证据不足 | PENDING_REVIEW，WATCH_20不消耗确认资格 |
| C：同日高点100→110 | 修订及复核，无市场新触档 |
| D：高点修订与新价格共同作用 | 候选待复核，不能混合不同单位确认 |
| E：同输入重复 | 不重复事件、不改写状态 |
| F–N | 同日变动、多档、恢复重入、窗口移出、边界、重标定、SPCX及单股待审全部通过 |
| O–T | 写入失败、恢复、迁移、旧阈值歧义、同ID升级、拒绝回滚、锁账本一致性全部通过 |

## 回归统计

| 测试类别 | 总数 | 通过 | 失败 |
|---|---:|---:|---:|
| test_market_calendar | 8 | 8 | 0 |
| test_yahoo_nine_offline | 18 | 18 | 0 |
| test_phase3 | 42 | 42 | 0 |
| test_phase4 | 17 | 17 | 0 |
| test_phase4_1 | 24 | 24 | 0 |
| test_phase4_1_guardrails | 6 | 6 | 0 |
| test_revision_diagnostics | 18 | 18 | 0 |

旧测试未删除或跳过。Phase4故障用例先迁移隔离夹具，再注入故障，完整保留字节不变断言；诊断B的旧缺陷预期改为要求保留候选。修复前失败和103项基线均已保存。

## 九股离线集成与迁移

从正式状态复制的隔离文件迁为v2：11条旧阈值歧义保留待复核，未自动确认或补发。重复迁移字节不变。
Phase2→Phase4价格仍识别1139条修订；九股指标、最高点日期及WATCH档位逐项等于原Phase4。无虚假市场事件；SPCX仍PASS_PROVISIONAL，SMA200=N/A。
当前隔离账本有12条待复核记录（11条迁移歧义及AVGO微小高点修订）。同份Phase4数据重跑九股NO_CHANGE，状态SHA256完全一致。

## 文件与兼容性

- 修改：src/monitor.py
- 修改：src/state.py
- 修改：src/signals.py (legacy API documentation)
- 修改：src/phase4.py
- 修改：diagnostics/revision_scenarios.py
- 修改：tests/test_phase4.py
- 修改：tests/test_revision_diagnostics.py
- 修改：README.md
- 新增：src/observations.py
- 新增：src/review.py
- 新增：tests/test_phase4_1.py
- 新增：tests/test_phase4_1_guardrails.py
- 新增：diagnostics/validate_phase4_1.py

数学规则版本不变，事件模型版本revision-market-v2。v1仍可只读验证，迁移仅在隔离副本，明确拒绝正式状态路径。原账本完整保留legacy_event_records；仅可信旧市场账本可支持确认，其余待复核。
使用 src.review --migrate / --list-pending / --event-id ... --decision CONFIRM|REJECT|KEEP --reason ... 明确操作隔离状态。拒绝修订需要有效旧检查点；已向前推进则停止，不擅自回滚较新状态。

## 验收结论

- P0_SIGNAL_DECOUPLING: PASS
- REVISION_FACT_PRESERVATION: PASS
- NO_FALSE_MARKET_CROSSING: PASS
- STATE_MIGRATION: PASS
- PENDING_REVIEW_LIFECYCLE: PASS
- ATOMICITY_AND_IDEMPOTENCY: PASS
- PROTECTED_DATA: PASS

## 保留风险

- Yahoo upstream precision cause remains unconfirmed; SPCX unresolved anomaly remains provisional.
- Unit comparability proof is deliberately conservative; real dividends/splits or missing provenance may need review.
- Legacy scalar transition(revision=True) is revision-only compatibility; full production monitor uses independent observations.
- Confirmed is a technical observation, never DELIVERED; no external notifications exist.
- Recovery to an older backup may restore older decisions; stable IDs permit reconciliation but no external delivery ledger exists.
- Real cross-day live validation remains pending; no Phase5 or network execution performed.

正式状态SHA256：`26e0f3f84e579b448e6e57fad9abd8b550568520c0088c0ff106f34eae727fa6`

本阶段无HTTP、调度、交易、外部投递或Phase5。
