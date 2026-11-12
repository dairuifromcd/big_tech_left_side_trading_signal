# 执行与恢复

运行声明只接受有常规交易时段且与指定aware时刻最近已收盘交易日一致的date。每date唯一；有RUNNING/UNCERTAIN_EXECUTION/STATE_ERROR运行时阻断新date。Cron重复可安全补设丢失Alarm，但不会绕过声明。

状态路径：READY → REQUEST_CLAIMED → EVIDENCE_SAVED → COMMITTED。原始证据一旦成功保存可离线重新计算，网络不能重发。Alarm至少一次投递不能等价于Yahoo exactly-once；本项目保证的是保守的at-most-once请求尝试，不确定时可能有意漏采并等人工核查。

| 异常点 | 本地行为 |
|---|---|
| 同日重复、两个scheduler | 唯一run/claim；不创建重复请求 |
| 重复Alarm | READY才可声明；已声明且不确定则停；完成后无重复请求 |
| 声明后、请求前中断 | 不能证明未发送；UNCERTAIN_EXECUTION |
| 请求后不确定 / raw保存失败 | UNCERTAIN_EXECUTION，不自动重采 |
| state或event提交失败 | SQL全部回滚；raw保留，可离线重处理 |
| 单/多标的数据失败 | DATA_ERROR；失败状态不推进，其他标的独立提交 |
| 429 | 全局停止本次后续采集，记录错误，不重试 |
| 401/403 | 单次保留失败；本次累计两次则全局停止 |
| 状态hash错/丢失/版本不兼容 | STATE_ERROR；禁止初始化重置 |
| 缺交易日 | CATCHUP_REQUIRED；保留旧checkpoint |
| 修订/来源无法证明 | 事件PENDING_REVIEW；不消耗confirmed阈值 |
| 原事件REJECTED新证据 | REOPEN_REQUIRED；保留旧决定 |

如果11月6日后直接看到11月11日，缺口包括9日及10日。后取完整history只可做RECONSTRUCTED_CATCHUP分析，不能称按时采集，也不能自动确认其事件。gapPlan只读输出缺口与顺序；validateArchive检查原始hash、aware capture时间、60秒允许差及同一完成交易日，且要求operator attestation。hash/本机时间不是独立认证。

可信归档应逐日由操作者核实后应用；完整应用runner尚未移植。本阶段只完成校验和阻断/计划测试，没有自动应用归档，也没有人工review界面。恢复既有待复核事件必须沿用ID，不能重建新的事件代替。

本地测试覆盖17项所列故障类别：存储单元测试、组合路径以及workerd真实SQLite回滚/实例重启/Alarm投递。进程内fault injection不是Cloudflare真实崩溃实测；远程重启、迁移、Alarm重试时延和长期调度可靠性均NOT_VERIFIED。

Alarms最多有限重试，不能作为无限可靠守护。后续需独立只读健康检测和人工恢复流程，不能在uncertain状态自动启用另一套采集任务。没有创建后台定时器、无限任务或恢复历史Phase4调度器。
