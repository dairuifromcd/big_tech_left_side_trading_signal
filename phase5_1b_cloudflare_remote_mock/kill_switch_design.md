# Kill Switch

KILL_SWITCH_READY: LOCAL_PASS。

初始化事务同时写入 `mock_experiment`：固定真实起止时间、20min 初始化截止、mode、runs/collectors/alarms、执行 fixture 与真实 UTC、ACTIVE/STOPPED、停止原因，以及 canonical SHA-256。恢复时核对 hash、整型上限和配置窗口完全相同。重部署延长期限会失败，不能复活 STOPPED。

- start 前检查截止、状态和最多 2 runs；按固定顺序，重复 fixture 不增加预算，不重采。
- 在实际 Collector 之前持久化 attempt 计数（最多 24），sync 后再检查过期/STOPPED/checkpoint。崩溃消耗预算，避免预算未计而已采集。
- Alarm tick 先持久化预算（最多 80），再执行一个标的。重复/过早 tick 消耗预算但保持 5s/批次间隔，不重采。
- 过期、预算耗尽、不确定执行、checkpoint 失败、显式 stop 均停止后续采集；H01 过期不创建 schema。
- stop 将 ACTIVE 变成终态 STOPPED、RUNNING 变 HALTED，storage.sync 后 deleteAlarm；读报告/status 不改变预算或业务状态。
- 未来任务晚于截止时只安排截止 Alarm，用于持久化停止；没有运行则无 Alarm。完成第二次任务立即停止并取消 Alarm。

本地证明：28 个 Node 测试含两次完整运行、窗口边界、20min/24h、sync 期间过期、重复/重叠/错误 fixture、90 次额外早到 tick、uncertain claim、预算损坏、窗口变更拒绝及重建 adapter；workerd 验证真实 Alarm、鉴权 stop、取消与重启后 STOPPED。测试结果见相应 JSON/日志。

80 是应用允许处理的 Alarm 预算。Cloudflare 至少一次交付，不能数学保证平台永远不投递一个迟到/已在途回调；此类回调不能触发采集或重新排程。真实平台调用总数必须另行核实，异常接近 80 即主动停止，不把应用计数冒充平台计费数。异常在 adapter 内捕获以避免应用主动触发平台重试；平台进程被终止等不可离线保证。

没有 Cron 不等于停止。必须同时验证持久化 STOPPED、Alarm=null、collector 计数不再增加，再撤销入口凭据。配额耗尽可能连 stop 的持久化写入也失败，此时需已批准的专用 Worker 停用/凭据撤销；不自动升级套餐。
