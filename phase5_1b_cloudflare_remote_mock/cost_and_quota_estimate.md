# 成本与额度估算

FREE_FEASIBILITY: **NOT_VERIFIED**。账户套餐、剩余配额和真实 Cloudflare 计量均未知。公开额度见 cloudflare_free_limits.md。

本地合成数据两次完整运行：24 calls、26 Alarm ticks、4,510 SQL statements、7,012 query rows returned、SQLite page bytes 737,280。SQL 数包含该测试的 checkpoint 和报告读取。后两项来自 Node SQLite，不是 Cloudflare rows-read/written 或账单。数字依测试代码及调用次数变化，可复跑。

拟议远程预算：1 Worker、1 SQLite class/namespace、1 固定实例；最多 2 次完整任务、24 collector attempts、80 处理 ticks；主动管理/报告请求 ≤200；窗口 ≤24h、无 Cron/R2/付费依赖。正常模型约 26 Alarm+≤200 RPC session，平台重复/拒绝请求另计。不以预计请求数当硬账户封顶。

若 DO 整个 24h 都以 128MB 计 Duration，粗上界为 0.128×86,400=11,059.2 GB-s；该估计不含控制宽限/额外平台活动，且同账户其他对象会共享日额度。实际每次约数分钟且可休眠，但不能以此声称免费可行性 PASS。窗口跨日也必须按 UTC 分日查询。

Worker 10ms CPU 是重要待验证风险：桥只做鉴权/小请求转发，指标计算在 DO；是否满足 Free 仍须真实计量。SQL 索引、触发器、Alarm/内部存储都会增加写入，当前不提供虚假的 SQL 计费上界。观察到 1102、配额拒绝、未知资源或升级提示立即停止，不自动付费。

仅当前账户已核实 Workers Free、SQLite DO 可用、共享剩余额度足够时，预期新增应付费用为 $0；这不是费用保证。当前费用结论仅 DOCS_ONLY_VERIFIED，不批准任何付费升级。公开入口的无效请求也可耗账户免费请求，不能从应用内部消除；需用户评估与批准。

Gate B 前不能用本地结果推算已验证的每月/每年成本。后续应从单次真实用量分别推算约 21 交易日/月和 252/年，并计入报告读取、复核、历史/备份增长和账户其他项目；备份不在本阶段开启。
