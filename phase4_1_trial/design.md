# Phase 4.1 修复设计（实施前）

严格离线；正式状态及 Phase 2–4 证据只读。当前仓库无提交、全部文件未跟踪，实施前完整源码快照、文件哈希、测试结果保存在 baseline/。

## 缺陷和最小变更边界

monitor.process_symbol 把任一历史差异变为 revision=True；signals.transition 的 revision 分支覆盖新日跨档，且仍合并触达资格。保留原有采集、指标公式、阈值及 abs_tol=1e-8/rel_tol=1e-10。新增独立 observations 层组合生产指标及原有市场事件规则；监控接口消费多个独立事实，单一 change_event 仅作兼容摘要，不是事实唯一来源。

## 双观察与可比性

revision_observation 保留全部逐日期差异、数值性质候选、指标影响及复核理由。market_observation 独立存储旧/新日期和价格、重新计算的旧基准/新基准、正常窗口移出、跨档、恢复与加深。必须检验同一证券、连续交易日、完整且一致的旧普通Close证据、前一交易日的Adj Close与复权比率锚，以及新旧窗口高点与跨档归因一致性。未知旧身份/Close或实质重标定、争议高点、边界敏感变化进入PENDING_REVIEW，不混合不同单位。微小金额本身不构成安全依据。

固定 B 的旧低价差异若不改变普通Close、锚点、窗口高点或跨档事实且有足够边界余量，可独立确认 -20% 市场观察；若输入不足，必须保留待复核事件而非丢失。原诊断合成器把Close设置为Adj Close，导致旧低价Close也改变，其B应保守待复核；另以Close不变的明确输入验证可确认路径。

## v2 状态与事件

observed、baseline、confirmed、pending 明确分离；triggered_thresholds 在v2仅作为confirmed兼容别名。baseline不代表通知，所有外部通知均未实施。每个阈值独立稳定ID：symbol/date/event_type/threshold/rules_version/event_model_version；不含运行时间或证据浮点噪声。修订事件与市场事件分开，状态变更和证据版本保留审计。待复核升级使用同一ID，只有确认后更新确认资格；同日重复不创造新事件，待复核不消失。

v1原账本完整保留legacy_event_records；只有可信账本证据可迁移为已确认市场观察，含糊的旧triggered_thresholds保留为迁移待复核，不自动补发市场事件。迁移只在隔离副本执行且幂等；load仍能只读验证v1。恢复和人工确认/拒绝/保持待复核必须明确指定对象及理由，不能依靠删除状态。

## 提交及验证

候选状态包含指标、证据和账本，一次原子提交；沿用flock、完整候选验证、三份版本备份、fsync及显式恢复。被明确拒绝的修订快照保留旧有效价格状态，拒绝决定及相关证据仍需留痕。修复前先保存P0失败证据；之后验证A–T、原有全部测试、Phase2/4隔离全流程、1139计数与指标相同、重复字节一致，最后校验正式状态和原有证据哈希。跨真实日期验证依旧待进行，本阶段无网络、交易或Phase5。
