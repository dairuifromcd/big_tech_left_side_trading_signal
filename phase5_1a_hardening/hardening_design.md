# Phase 5.1A 安全加固

范围仅为 H01 Safe Initialization 与 H02 Full Checkpoint Preflight。初始 HEAD 为 `a324465ee094dbf733acabe9e142251a3841ab79`，初始工作区干净，项目内未发现 AGENTS.md，遵循用户提供的工作原则。未实施 Phase 5.1B/5.1C，未提交或推送。

沿用已经读取的 Cloudflare durable-objects skill；平台依据为官方 [SQLite storage](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/)、[DO RPC](https://developers.cloudflare.com/durable-objects/best-practices/create-durable-object-stubs-and-send-requests/)。同步事务用于验证与启动的原子性，初始化期间 blockConcurrencyWhile 仅覆盖初始化与存储确认，没有外部网络调用。

H01：默认禁用的内部初始化 RPC，经独立 credential、明确的操作意图与精确目标 DO ID 校验后才能执行。存储必须没有任何可见旧应用 schema，即使旧表已清空也拒绝。receipt、schema、审计及安全控制表在同一个 SQLite 事务中创建。失败回滚，绝不删旧数据或补造 baseline。

H02：Coordinator.start 在同一个事务中完成全 checkpoint 验证、运行声明、12个任务声明及验证标记。验证状态、事件、证据、audit、跨状态引用、原始数据/最新状态/历史DTO关系。损坏或尚未支持的旧格式在 Collector 前阻断。

日内优化采用数据库 generation 与18个写入触发器。状态、事件、原始证据、历史DTO、初始化元数据与初始化审计的任何写入都使先前验证过期。每次请求前只检查 guard、触发器定义和 generation/运行标记；不重复扫描全部事件。受控 raw 保存和单标的提交在各自事务内验证实际写入并推进标记。未知改写必须停止，不能用缓存直接放行。

补充的最小关联修复：提交时禁止 pending 自动升级、rejected 自动重开、旧证据/audit 前缀改写及依赖复核标记删除；其他标的事件不能在本标的提交中被修改。内部状态错误保留 STATE_ERROR 分类。没有改变指标公式、阈值、观察池或稳定事件ID字段。

测试输出迁至新的 phase5_1a_hardening，默认也不会写旧 Phase 5.1 验收目录。原135项 TS 测试全部保留，旧 Python/Golden/历史文件作为只读基线。

本地成功不等于真实平台认证、资源额度或远程初始化已验证。所有云端激活、Secrets、资源和调用身份均保持未配置；下一步只能人工审阅。
