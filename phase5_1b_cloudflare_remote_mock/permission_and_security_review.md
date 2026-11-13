# 权限与安全审查

当前授权仅 Gate A。没有有效 Gate B 批准，没有新增认证，也没有 Cloudflare 修改。

| 范围 | 最小需求 / 当前结论 |
| --- | --- |
| 账户调查 | 账户和订阅只读、Worker/DO metadata、Cron、用量；权限 NOT_VERIFIED |
| 新建 Worker/SQLite DO 类 | 新资源创建权限；创建后尽可能限单个 Worker 的 Editor，不能擅自扩大 OAuth |
| 部署/Secret 管理 | 仅候选 Worker 的脚本、版本、deploy、绑定、Secret 写权限 |
| 指标 | 对目标 Worker/namespace 的 metrics/logs 只读；不可获取项标 NOT_VERIFIED |
| 应用初始化 | 一次短期初始化 Secret，仅精确实例，20min 时效 |
| 应用控制 | 独立控制 Secret，仅五条固定管理路径，窗口 + 1h 停止宽限 |
| 报告 | 独立 REPORT_TOKEN，仅 GET，不可初始化/控制 |

官方支持 Worker 粒度角色；新建权限与现有 Worker 的编辑权限不同。现有插件实际授权无法查询，不能假定具备任一写权限。参考 [Workers roles](https://developers.cloudflare.com/workers/authorization/workers/)、[API permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)。旧权限名 `Workers Scripts Write/Read` 与新角色的对应、DO/订阅/Analytics 端点权限，需工具恢复后按精确 endpoint 核实；不要求 Read All 或账户 Owner。

本机管理程序使用内存随机 Secret，不在命令行参数、Git、shell history、报告或日志保存值。如 cf 必须通过 secrets-file 上传，仅可用项目内 ignored 临时 JSON、0600 权限、关闭 tracing，完成后删除；禁用 dotenv 展开和 CI 自动登录。当前没有创建真实 Secret 文件。项目 `.home` 为空，cf 认证方式尚需用户明确批准，不能读取或复用用户目录 OAuth 文件。

默认远程开关关闭，管理/报告拒绝，不自动初始化。初始化不确定就停止；完整 checkpoint 错误停止；未知远程资源/付费要求/非 Mock 出站立即停止。紧急操作仅能 stop 本对象、取消其 Alarm、撤销本 Worker 的凭据，不能修改其他项目。

外部影响需审批：共享账户请求/SQL/存储配额、workers.dev 临时暴露、凭据上传、最多两个显式部署及 Secret/flag 撤销产生的版本变化。可通过 stop+撤销凭据恢复到不可执行状态。更小暴露替代方案是由用户自行提供已有可信内部调用方；当前不假设其存在，也不新增第二个 Worker。
