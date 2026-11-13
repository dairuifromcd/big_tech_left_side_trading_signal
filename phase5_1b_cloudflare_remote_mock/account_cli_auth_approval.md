# 历史提案状态更新 — 2026-11-13

用户已选择 Dashboard 人工核验并提供 USER_REPORTED_DASHBOARD 结果；下方 `p51b-readonly` 提案未执行、已被本次方案替代，不再等待其批准。没有创建 Profile、OAuth 或 API Token。未来 Gate B 认证方案以 `gate_b_authentication_plan.md` 为准，仍只供审批。

---

# CLI 只读认证提案：等待批准，未执行

2026-11-13；本次只处理账户核验。Gate B、原实验时间、资源和管理入口均未改变。

## 已确认的能力与边界

项目已有 `cf 1.0.0-beta.29` 和 Node 22.23.0，无需安装或升级。官方 [cf 入门](https://developers.cloudflare.com/cf/get-started/) 和 [coding agents 文档](https://developers.cloudflare.com/cf/agents/)说明：本地 search/schema/help 无需登录，正式查询需要独立 CLI 认证。插件登录不能代替 cf Profile。

`account_cli_readonly_preflight.json` 保存实际 help/schema 输出；本轮只运行这些本地命令，没有运行带认证的 API 查询，也未运行 auth whoami 以触发可能的刷新。

| 目的 | 本机验证的命令 | schema / 限制 |
| --- | --- | --- |
| 可访问账户 | `cf accounts list` | GET `/accounts`；分页 |
| 套餐/订阅 | `cf accounts subscriptions get` | GET `/{account_or_zone}/{account_or_zone_id}/subscriptions`；账户模式，勿传 zone |
| 权益/分配额 | `cf accounts entitlements get` | GET `/{account_or_zone}/{account_or_zone_id}/entitlements`；实际返回覆盖情况待验证 |
| Workers 清单 | `cf workers list` | GET `/accounts/{account_id}/workers/workers`；分页，不是猜测的 scripts list |
| Worker metadata | `cf workers get <worker>` | GET `/accounts/{account_id}/workers/workers/{worker_id}` |
| DO namespace / backend | `cf durable-objects namespaces list` | GET `/accounts/{account_id}/workers/durable_objects/namespaces`；分页 |
| 用量信息 | `cf billing usage get-info-v1` / `get-account-usage-v2` | GET；Alpha/Restricted，不保证所有账户可用或覆盖 UTC 日免费余额 |

当前 `workers scripts --help` 仅列出 search。`workers scripts schedules` 和 `subdomains` 返回 Unknown command；不能把官方 REST 端点名称直接当作本版本 CLI 子命令。Cron、现有 workers.dev 和无法取得的额度须用 Dashboard 补充。未创建资源不能实证“账户可成功创建 SQLite DO”；只可结合当前套餐/权益与官方产品说明判断，保留部署验证缺口。

项目 `cloudflare/.home` 文件数 0；项目/根目录均无 `.env`；未注入 API Token/Auth Profile。仅检查存在性，不读取个人认证文件或凭据值。阻断为 `CLI_AUTHENTICATION_REQUIRED`，而非插件必须修复。

## 提案：项目隔离的只读 Profile

**以下只是审批内容，不要在批准前执行。** 候选 Profile 名 `p51b-readonly`，通过 `auth create` 的显式 `--scopes` 登录；每次查询使用 `--profile p51b-readonly`，不执行 activate，不改变任何默认 Profile。

拟申请的 OAuth scopes：

| Scope | 读取目的 / 风险 |
| --- | --- |
| `user:read` | 登录身份核对；可能读取邮箱等个人身份，不写入报告 |
| `account:read` | 账户及权益 metadata；可能列出多个可访问账户 |
| `billing:read` | 订阅、套餐及用量；可能看到其他产品账单 metadata，不查询付款方式/发票 |
| `workers:read` | Workers/DO metadata；权限可能比单条名称查询更广，但没有部署/修改权限 |
| `account-analytics.read` | 账户用量/分析；可能看到其他项目汇总，报告仅留本任务所需总量 |
| 自动附加 `offline_access` | CLI 实现自动申请刷新能力，会保存 refresh token；不是一次性无持久授权 |

这五项 read scope 均存在于锁定 CLI 的 scope 集。OAuth 同意页可能受账户/服务端支持限制，不能预先保证每个 GET 都获准。若同意页要求不同/更多权限，或查询返回 401/403，立即停止，不增加权限。

**不能直接运行不带 scopes 的 `cf auth login`。** 锁定版本的默认 scopes 包含多个产品的 write 和 token-create 权限，超出当前任务。也不采用 API Token 创建方案，因为创建 Token 本身需要额外授权。[订阅 API](https://developers.cloudflare.com/api/resources/accounts/subresources/subscriptions/methods/get/) 接受 Billing Read；[DO namespace API](https://developers.cloudflare.com/api/resources/durable_objects/subresources/namespaces/methods/list/) 接受 Workers 的读取权限。

拟议命令参数为 `auth create p51b-readonly --no-browser --scopes user:read account:read billing:read workers:read account-analytics.read`，必须通过已审阅的完整 child-process 环境调用项目 Node 和项目 cf；不应复制后在未限定环境的终端执行。设备授权由用户在浏览器完成，不使用 localhost callback、不自动打开浏览器、不申请部署能力。

## 精确写入路径和项目外影响

项目根为 `/Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal`。拟议 child-process 环境仅对该进程设置 XDG_CONFIG_HOME、XDG_CACHE_HOME、TMPDIR，关闭 telemetry，并设置 `CLOUDFLARE_AUTH_USE_KEYRING=false`；不改 HOME、shell 配置或持久环境变量。

- 凭据文件：`/Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal/cloudflare/.home/cloudflare/config/p51b-readonly.json`。锁定实现以 0600 写入，含 access/refresh token，禁止进入 Git/日志。
- 配置根：`/Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal/cloudflare/.home/cloudflare/`。若 CLI 生成偏好 metadata，可出现 `preferences.json`；不执行 activate，因此不应创建 `profiles/directory-bindings.json`。出现未列写入先停止。
- 缓存/临时文件：本项目 `cloudflare/.cache/`、`cloudflare/.tmp/`。账户选择可能产生 `cloudflare/node_modules/.cache/cloudflare/cloudflare-account-p51b-readonly.json`（或项目 `.cloudflare/cache/`）；优先每次显式传已确认的账户环境变量避免自动选择。
- 明确禁止写入：默认 macOS 配置根 `/Users/rui/Library/Preferences/cloudflare/`、其他用户认证目录、shell 配置、Codex 配置，以及 macOS Keychain。关闭 keyring 也避免其原生依赖自动安装或凭据迁移。
- 项目外实际影响：用户浏览器需批准 Cloudflare OAuth，Cloudflare 身份系统新增该客户端授权；它不是资源部署，但仍是必须批准的账户授权变化。OAuth 可能覆盖该用户可访问的多个账户，不能保证由本地目录隔离成单账户权限。后续查询只明确选择用户指定账户。

plaintext JSON 即使 0600，也有本机泄露/备份风险；refresh token 可持续读取，直至过期或撤销。不得将文件内容、设备授权码、Token 或 Cookie 发到聊天或 Git。

## 恢复与更安全替代

如批准认证，建议同一批准同时涵盖核验结束后的撤销：仅对本次 Profile 的 OAuth refresh token 执行 logout/revoke，再移除该 Profile 和专用缓存；不影响既有默认 Profile。撤销会写 Cloudflare 身份系统，删除凭据会写项目文件，因此也要明确批准，不能现在自行执行。仅删除本地文件不等于云端授权已撤销。

更安全替代是由用户按 `dashboard_readonly_checklist.md` 使用已有 Dashboard 会话手工核验：无需新 CLI Profile、OAuth 或 Token。当前已提供该方案，尚未收到账户级证据。

## 当前暂停点

`AUTHENTICATION_STARTED: false`；`PROFILE_CREATED: false`；`CLOUD_RESOURCE_MUTATIONS: 0`。

按用户本轮第 3 条要求，若继续 CLI，需先批准上述限定路径、五项 read scopes + 自动 offline_access、Cloudflare OAuth 授权影响，以及结束后的专用 Profile 撤销/清理；不包含 Gate B。否则选择 Dashboard 核验。本轮到此停止，不登录、不升级 CLI、不改实验窗口、不激活入口。

路径和自动 scopes/keyring 细节来自项目已安装的官方 cf 包：`cf-DmvZ2L51.mjs`（getCfConfigPath、JSON profile、directory bindings、默认 scopes）与 `chunk-Q5KVZMHK-WOCEMyET.mjs`（0600、offline_access、keyring 行为）。这是对锁定版本源码的结论，不冒充账户实际权限证据。
