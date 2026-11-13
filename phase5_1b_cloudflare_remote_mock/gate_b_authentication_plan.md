# Gate B 认证设计（方案，不执行）

GATE_B_AUTHENTICATION_DESIGN: READY_FOR_AUTHORIZATION_REVIEW；ACTUAL_GRANTS / CLI_ACCOUNT_ACCESS: NOT_VERIFIED。本次没有认证、Token 创建、个人凭据读取、Keychain 或用户级配置修改。Dashboard 证据不证明 CLI 登录或部署权限；历史只读 Profile 提案已撤回。

## 权限与工具边界

2026-11-13 官方文档说明 Workers 支持产品级及指定 Worker 的权限。首次创建需要 Workers 产品级 **Admin**，无法给不存在的 Worker 分配单 Worker 权限；创建后，指定 Worker 的 **Editor** 可部署及管理 Secrets。该角色也能修改该 Worker 其他设置，无法限制只写某三个 Secret 名称。这是服务端权限粒度限制，名称白名单只能由操作清单约束。[Workers 权限](https://developers.cloudflare.com/workers/authorization/workers/)

| 未来操作 | 最小权限设计 / 精确目标 |
|---|---|
| 首次创建 | 目标账户的 Workers 产品级 Admin，仅 bootstrap 时短暂使用；作用于该账户全部 Workers，不能声称只影响候选名 |
| 后续代码、绑定、Secret put/delete | 仅 `us-stocks-p51b-mock-20261113` 的 Individual Workers Editor；不申请所有产品管理权限 |
| SQLite class / namespace | 由实现 Worker 的 exports / 绑定创建；DO 无独立角色，沿用实现 Worker 权限；不申请虚构 DO write scope |
| 真实 Worker / DO 指标 | 该 Worker 的 Individual Workers Metadata Read-Only；不读取 DO 原始数据、Data Studio 或其他 Worker 内容 |
| 账户汇总余额 / 套餐 / Cron | 用户 Dashboard 手动复核；不为补齐可见性申请账户 analytics/billing 权限 |
| 数据面 init/start/stop/report | 三个独立随机 Secret（各至少 32 random bytes）；不是控制面 API Token，固定对象/路径/窗口 |

DO 的权限和可观测性遵循实现 Worker 的角色。[DO 权限](https://developers.cloudflare.com/workers/authorization/durable-objects/)。Secret PUT 接受 Individual Workers Editor；旧 API 还列 Workers Scripts Write，但不因此默认采用账户级旧权限。[Secret API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/secrets/methods/update/)

## 推荐未来路径与必须审阅的权限风险

推荐由用户用既有 Dashboard 权限亲自完成**第一次显式部署**（精确上传审阅包及绑定，不运行应用初始化）。代理不读取该浏览器凭据。首次创建不能在服务端限定为一个新名称，是不可绕过的 bootstrap 权限边界。若 Dashboard 无法上传该 cf exports 包，立即停止并重新审阅；不能隐式改用旧 migration 模式。

后续可在用户单独批准后，由用户创建短期、单 Worker Editor API Token，另建只读 metrics Token，设置最短可行 TTL。Token 仅经项目隔离子进程 `CLOUDFLARE_API_TOKEN` 注入；**本次没有创建或使用**。`cf` 官方支持该环境变量并优先于 Profile，且不支持 Global API Key。[cf 认证选择](https://developers.cloudflare.com/cf/get-started/)

如果用户希望代理用 cf 完成首次部署，需另外明确批准短期 Workers 产品级 Admin Token 的 bootstrap 风险（可影响现有全部 Workers），创建后立即撤销、换为单 Worker Editor。它不是默认方案，也不是账户所有产品的全权限。未经这一单独选择，代理不能执行首次 cf 部署。

锁定 `cf 1.0.0-beta.29` 的项目 Profile 机制能隔离本地文件；OAuth scopes（如 workers:write）不能声明指定 Worker 资源，并且含刷新能力，不能当作单 Worker 最小权限。**不推荐 OAuth 路径，不执行 `auth login/create/activate`**。若未来单独批准 OAuth，必须由用户浏览器完成同意，并重新列出 scopes/refresh/revoke；不能沿用旧 readonly 批准或默认全 scope 登录。

cf 文档和本地源码只证明支持认证输入，不证明 Beta CLI 所有部署内部端点都接受新粒度权限。未来部署前逐端点复核本地 schema / 请求计划；要求账户广泛列表、额外写权限、资源、或返回 403 时停止，不自动扩权。当前 compatible_cf_granular_token: NOT_VERIFIED；这限制执行资格，不妨碍本次将方案提交授权审阅。用户可选择保留人工部署路径。

## 本地位置、项目外影响和恢复

项目根 `/Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal`。未来进程隔离使用 `cloudflare/.home`、`.cache`、`.tmp`，关闭 telemetry/keyring，清除继承的认证环境变量并显式指定账户；不改变 HOME、shell、默认 Profile 或系统设置。不安装/升级工具。

推荐 Token 只存在用户控制的进程环境，**无凭据文件**；不得写入 `.env`、日志、manifest 或 Git。若未来另选 Profile，候选文件为 `cloudflare/.home/cloudflare/config/p51b-deploy.json`（0600，含 access/refresh token）；这是锁定 CLI 实现推导的拟议位置，不是本次创建事实，须另批。缓存仅限 `cloudflare/.cache`、`.tmp`、`.home/cloudflare` 和项目 `node_modules/.cache/cloudflare`；不读默认个人认证根或 Keychain。

未来授权必须包含：具体账户/Worker、角色、TTL、Secret 名称、两次部署上限、身份核验、Token/Secret 撤销和项目缓存清理。项目外影响是 Cloudflare 授权、版本、绑定和数据面的实际变化；风险包括 bootstrap 可触及其他 Worker、单 Worker Editor 可修改源码和设置、凭据明文暴露、共享额度及公开入口请求。恢复为仅停止目标、取消 Alarm、撤销临时授权，保留原始状态；不能通过重新初始化恢复。

撤销顺序：先导出脱敏证据 → STOPPED + Alarm=null → 删除三个数据面 Secrets/验证拒绝 → 用户在 Dashboard 撤销专用控制面 API Tokens（或另批 OAuth grant）→ 清除子进程凭据及本项目专用 Profile/cache。Token 撤销后才能删本地副本；删除文件不等于服务端撤销。只影响新建临时凭据，不能 logout 既有个人登录。撤销/Secret 操作本身是未来账户写入，须包含在批准中；未批准时不执行。更安全替代是用户全程人工部署及撤销，代理只提供审阅包和检查表。
