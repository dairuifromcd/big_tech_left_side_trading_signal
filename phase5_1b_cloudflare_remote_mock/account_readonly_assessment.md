# Cloudflare 账户只读调查

调查日期：2026-11-12 UTC。CLOUDFLARE_ACCOUNT_VERIFICATION: NOT_VERIFIED。

1. 初始会话没有 Cloudflare 工具，插件搜索返回空。仅说明会话工具发现结果，不否认用户已安装/连接插件。
2. 用户确认插件已连接后，出现 `cloudflare_search/execute/docs/whoami` 工具元数据。
3. `search`、`whoami`、`docs` 均返回 MCP `-32001 Unknown tool`，未返回账户信息。没有调用 execute 执行远程操作。
4. 项目 `.home` 文件数为 0；仅检查环境凭据是否存在（API token/key 均不存在），没有输出或读取凭据值。未读取用户目录认证文件。
5. 本地 `cf` 1.0.0-beta.29 的 auth/account/deploy help 可读取。没有运行 login/create/activate，没有修改用户配置或 OAuth。

| 项目 | 结论 |
| --- | --- |
| 目标账户脱敏标识、当前 Workers 套餐 | NOT_VERIFIED |
| 当前账户 Free、SQLite DO 权益 | NOT_VERIFIED；公开文档支持 Free SQLite DO |
| 已有 Worker 数量、DO 类/命名空间、Cron | NOT_VERIFIED |
| 当前用量、剩余额度、账单依赖 | NOT_VERIFIED |
| 候选名称冲突、workers.dev 子域 | NOT_VERIFIED |
| 现有授权是否足够读账户/部署/指标 | NOT_VERIFIED |
| cf 配置和资源模型 | 本地 build/dry-run PASS；账户可部署性 NOT_VERIFIED |

工具恢复后，只读查询应分页读取：账户及套餐/订阅、Worker 列表与 schedules、DO namespace/class 列表、workers.dev 设置、当前 UTC 日的 Workers/DO/SQL 用量及权限信息。只保存相关数量和脱敏目标；不读取其他项目源码或 Secret 值。不以“没有订阅记录”单独证明 Free。

账户查询未成功，不能确定最终资源名。CLI 没有项目认证；插件连接也不等于 CLI 已认证。Gate B 仍需可用的账户只读证据及单独批准的项目范围 cf 认证方式。禁止导出插件内部 Token。若所需查询或授权不可用，停止该路径，不能自行扩大权限。
