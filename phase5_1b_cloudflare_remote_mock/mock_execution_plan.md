# 有限 Mock 执行计划

仅本地模拟已执行；以下远程步骤待 Gate B 授权。

拟定窗口：**2026-11-14T00:00:00Z ≤ real UTC < 2026-11-15T00:00:00Z**。初始化截止 00:20 UTC；20min 后尚未完成初始化则放弃，不得顺延。批准晚于可用窗口时必须重提时间和 manifest。

窗口修订说明：2026-11-12 23:26 UTC 仍未获得 Gate B 批准，原拟 11 月 13 日窗口撤回；本次改为上述 11 月 14 日候选窗口，须明确批准，不继承任何旧时段权限。

显式 fixture 日期依次为 `2026-11-06`、`2026-11-09`。生产 `Coordinator.start()` 的 `latestSession(now)===date` 原封不动；专用 adapter 只在内部从固定 fixture calendar 推导模拟时间。外部 start 只接收 fixture_date，不接收 now、asof、任意日期或行情。budget.executions 保存真实 UTC，原始证据带 SYNTHETIC provenance；历史计算时间与真实运行时间分开。原数据不导入，不宣称历史 PIT。

最多两次、每次固定 12 标的顺序；最多 24 次采集，最多处理 80 次 Alarm。第一次 baseline 无市场事件；合成 ^SOX 约 30%+ 回撤，WATCH_30 不应生成新触档事件。第二 fixture 延续同一合成价格序列，验证 H02、版本、历史及无重复事件。

本地模型：两次共 26 ticks、24 calls、12 states、24 evidence、0 events，六类报告只读；5s 全局间隔、每三标的跨批次额外 30s。依下一条 claim 的实际 finished+间隔安排 Alarm，空任务再一次 tick 标记 COMPLETE。所有间隔使用真实执行 clock；没有长等待 loop。

远程顺序：初始化与撤销 init → 首次 start → 小次数轮询 → 六类 API/状态读取 → 同 fixture 重复 start → 新 Stub 读取 → 第二 fixture → STOPPED/Alarm=null → 导出证据 → 撤销凭据。管理/报告主动请求合计预算拟定 ≤200，不能通过持续轮询扩大范围。非授权外部访问不受这个客户端预算控制。

故障隔离、重复/提前 Alarm、uncertain no-recollect、过期/计数停止已在本地测试；远程入口没有 SQL/fault/手动 alarm 后门。`alarm` 是平台保留 RPC，不能像普通 RPC 人工调用。云端若未自然观察到重复交付或驱逐，只标 NOT_VERIFIED；不得为凑验证频繁部署或新增测试钩子。重新获取 Stub、本地 workerd 重启、Worker 重部署、真实云端驱逐分别记录。

Cloudflare CPU、Duration、内存、1102、请求/SQL/存储计量须按实际 Worker/namespace 和 UTC 窗口读取；Node 的时间和 rows-returned 不能替代。工具不支持的指标标 NOT_VERIFIED，不进入 Phase 5.1C。
