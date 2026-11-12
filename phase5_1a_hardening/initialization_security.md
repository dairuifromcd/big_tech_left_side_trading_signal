# H01 安全初始化

管理入口是 `ExecutionCoordinator.initializeIsolatedMock(command, credential)`，仅通过内部 Durable Object binding/RPC 调用。普通 Worker HTTP handler 和 Dashboard API 没有任何分支转发到该入口。默认 cloudflare.config.ts 不提供初始化 policy 或 secret，不启用 LOCAL_TESTING。

调用必须同时满足：

1. `MOCK_INIT_ENABLED` 明确为 `EXPLICIT_ISOLATED_MOCK_V1`。
2. 配置独立、至少32字符的 `MOCK_INIT_TOKEN`，对固定长度摘要进行 timingSafeEqual 比较。
3. `MOCK_INIT_OBJECT_ID`、实际 ctx.id 与 command.target_object_id 完全一致。
4. operation 是 `INITIALIZE_EMPTY_ISOLATED_MOCK`，提供非空 request_id、operator、authorization_reference、reason；字段有长度上限。
5. DO 原生 KV list 为空，没有已设 Alarm；SQLite 不存在任何可见旧应用表、视图、索引或触发器。空旧表也拒绝。

通过授权后，在 blockConcurrencyWhile 内执行空库检查与初始化。SQLite DDL、receipt、receipt hash、schema、initialization_audit 及 checkpoint 控制行一次事务完成。任一点失败回滚全部新内容。预期拒绝在 blockConcurrencyWhile 内捕获、在外部返回错误，避免逻辑拒绝重置健康实例。

receipt 包含 operation、精确目标、请求/操作者/授权说明、UTC时间、随机 receipt_id、receipt/schema版本、DRY_RUN_MOCK_ONLY、rules和两类event model版本。meta receipt与独立审计行内容/哈希必须一致；正常 guard 每次核对，并在 DO 中绑定实际对象身份。credential 不写入receipt、审计或日志。

初始化只接受新实例。重复调用、新request_id、换token、删除receipt、清空旧表均不能使既有schema再次获得初始化资格。没有删除、清理或强制重置选项。外部有权完全删除数据库/namespace的管理员不在本地hash防护能力范围内；未来必须同时限制这些Cloudflare权限，不能把SHA256当作防恶意管理员签名。

旧 Phase5.1 scratch数据库的字面 receipt 不能冒充本阶段可验证receipt：明确 `LEGACY_INITIALIZATION_MIGRATION_REQUIRED`，不自动补receipt或迁移。这里不实施旧状态迁移。

本地演练：

```sh
node cloudflare/scripts/local.mjs initialize-local
```

工具只有本地模式，无远程URL、账户或namespace参数。使用现有Worker bundle、项目内临时数据库、内存随机测试credential和禁用出站的Miniflare；关闭后停止运行。日志只保留receipt标识/时间与出站计数，不输出credential。

发现 Miniflare SQL检查器会自动建立 `__miniflare_do_name`，因此本阶段禁用该检查器。没有在初始化代码中忽略此表或放宽非空存储判断，另有测试确保类似系统表命名的旧数据也被拒绝。

未来激活路径：经过单独人工授权的内部管理调用方 → 精确目标DO的该RPC。若没有可信内部调用方，Phase5.1B必须先审查其调用身份、最小权限和入口保护；本阶段没有创建管理Worker、公开HTTP接口或远程调用工具。不得为了激活而开启LOCAL_TESTING。真正Cloudflare调用身份、Secrets绑定和初始化结果均 NOT_VERIFIED。
