# 核验结果更新 — 2026-11-13

用户已按 Dashboard 路径完成只读核验并在任务中报告结果，标记 USER_REPORTED_DASHBOARD。摘要见 `dashboard_account_evidence.json` 与 `account_readonly_assessment.md`。以下原始清单保留为未来部署前重新确认用途；表中 NOT_VERIFIED 为历史空白模板，不是对本次已报告项目的否认。未报告的精确时间/时区、Workers 用量及真实部署权限仍未验证。Gate B 未获批准。

---

# Cloudflare Dashboard 手动只读核验

目的：用户使用已有 Dashboard 登录会话核实账户，避免新增 CLI 认证。**这些步骤尚未由代理执行，所有待填项仍是 NOT_VERIFIED。** 不创建测试资源来“验证可用”。

## 1. 选择账户与核实套餐

1. 打开 [Cloudflare Dashboard](https://dash.cloudflare.com/)，在账户选择器选定目标账户；记录核验 UTC 时间和脱敏账户引用（如仅后 4 位），不要提交完整 URL 中的账户 ID、邮箱、付款信息。
2. 进入 **Compute (Workers) → Workers & Pages**（部分界面直接显示 Workers & Pages），查看 **Account details / Plan / Plans** 中 Workers 的当前计划。必须是 **Workers Free**；某个网站/域名的 Free 套餐不是 Workers Free 证据。
3. 在 **Manage account → Billing → Subscriptions** 只读核对是否存在 Workers Paid、试用、待付款或其他相关订阅。记录 Workers 计划标签与状态；不打开/复制卡号、地址或发票，不点击 Upgrade、Subscribe、Cancel、Enable 等按钮。
4. 若套餐不明确，或只有“未发现订阅”，仍标 NOT_VERIFIED。不能凭没有账单认定 Free，也不为核验切换套餐。

## 2. Workers 清单和命名冲突

1. 回到 **Workers & Pages → Overview**，选择 Workers 筛选，查看所有分页，记录 Worker 总数；Pages 项目不要混计为 Worker。
2. 使用搜索框逐字搜索候选名称 **`us-stocks-p51b-mock-20261113`**，记录存在/不存在及核验时间。存在则停止，不覆盖、不改名、不删除。
3. 在 Account details/Settings 中只读查看既有 **workers.dev subdomain**；若仅有 Set up/注册提示，记录“尚未设置/未验证”，不要创建。只需记录“是否存在”，不必公开完整生产子域。
4. 不访问任何已部署 Worker URL、不运行 Preview/Send/Test，不编辑代码或设置。已有 Worker 的 HTTP 请求本身可能触发应用逻辑。

## 3. SQLite Durable Objects 权益及 namespace

1. 进入 **Storage & databases → Durable Objects**（有些界面位于 Compute 下），查看现有 namespace 列表和账户用量。
2. 遍历分页，记录 namespace 总数、可见的 SQLite/KV 后端数量；对相关项记录 class 与关联 Worker metadata，不打开原始对象数据或 SQL explorer。
3. 查找 **`RemoteMockCoordinator`** 及候选 Worker 的关联。类名相同但属其他 Worker 时也记录并交由后续审阅；不得复用任何现有 namespace。只保留本任务相关名称，其余项目用数量汇总即可。
4. 若列表/详情明确显示 SQLite，可作为已有 namespace 后端证据；若没有 backend 字段则标 NOT_VERIFIED，不能根据 namespace 名字推断。
5. 若页面显示需要升级或启用，停在提示页，不点确认。结合已核实 Workers Free 与官方 [DO pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/) 对 Free SQLite 的说明记录产品资格；“未部署情况下实际能否创建/初始化”仍未验证。
6. 固定实例名 **`phase51b-synthetic-20261113-v1`** 只属于未来新 namespace；当前不能证明它在未创建 namespace 中存在/为空。不要创建对象或调用它来核验，保持 `INSTANCE_ID: NOT_CREATED`。

## 4. 免费额度、当前用量与证据时间

1. 查看 Workers & Pages 的账户 Usage/Account details 卡片，记录今日请求 used/limit。必须记录 **UTC 今日 00:00 至核验时刻**；图表的“最近 24 小时”不是同一统计窗口。
2. 在 Durable Objects 页面先看 **账户级 Usage**：requests/RPC/Alarms、Duration、SQLite rows read、rows written、总存储。记录界面实际值、单位、时区、所选窗口和可见上限，不填推测值。
3. 若账户总量缺失，可进入既有 namespace → **Metrics** 只读查看，但不能将单 namespace、单对象或分位数图当成整个账户的剩余额度。[官方 DO metrics](https://developers.cloudflare.com/durable-objects/observability/metrics-and-analytics/)说明默认最近 24h，可筛选对象；注意取样与延迟。
4. Workers 的单脚本 Metrics 也只能作为该 Worker 的活动数据；[官方 Workers metrics](https://developers.cloudflare.com/workers/observability/metrics-and-analytics/)说明存在聚合延迟。未展示的 SQL/存储/配额写 NOT_VERIFIED，不把空图当成 0。
5. 可在 Billing → Usage / Billable usage 交叉核对，但账单月用量不等于 UTC 日额度。不得启用日志、Analytics 或其他服务来补齐指标。
6. CPU/内存只记录已有 metadata/图表；本轮没有远程 PoC，所以“本 PoC 真实 CPU/内存”等仍为 NOT_VERIFIED。

## 5. Cron 与入口保护

1. 对所有现有 Worker，从 Overview 选中 → **Settings → Triggers / Trigger Events → Cron Triggers**，只读记录条数，合计账户总数。可参考 [官方 Cron 文档](https://developers.cloudflare.com/workers/configuration/cron-triggers/)。
2. 未遍历全部 Worker 就不能声称账户 Cron 为 0。只统计，不点 Add/Delete/Save。
3. 若需要了解已有访问保护，仅读取 Settings → Domains & Routes / 既有 Access policy metadata；不新建 Access 应用、域名或策略。本次测试 Worker 未创建，因此其实际 URL 和保护状态仍未验证。

## 6. 返回最小核验结果

可以仅提供下面的脱敏文字；不需要任何 Token、Cookie、认证码或无关项目源码。若截图，仅保留相关标签和数值，遮盖邮箱、完整账户 ID、付款信息和无关项目名。

| 项目 | 待填写 |
| --- | --- |
| 核验 UTC 时间 / 脱敏账户引用 | NOT_VERIFIED |
| Workers 当前计划 / 订阅状态 | NOT_VERIFIED |
| Worker 总数 / 候选名是否存在 | NOT_VERIFIED |
| DO namespace 总数 / SQLite 可见证据 | NOT_VERIFIED |
| 候选类与关联 Worker 是否存在 | NOT_VERIFIED |
| Workers 请求 used / limit / UTC 窗口 | NOT_VERIFIED |
| DO 请求、Duration、SQL read/write、存储 used / limit / 窗口 | NOT_VERIFIED |
| Cron 总数 / 是否已遍历全部 Worker | NOT_VERIFIED |
| 既有 workers.dev 子域是否已设置 | NOT_VERIFIED |
| 升级提示、权限不足或无法取得的项目 | NOT_VERIFIED |

用户提供的 Dashboard 结果应标记为 `USER_REPORTED_DASHBOARD`，与代理通过 API 直接验证区分；未提供或不可见项目保留 NOT_VERIFIED。人工核验不是 Gate B 授权，也不表示实验时间可顺延。
