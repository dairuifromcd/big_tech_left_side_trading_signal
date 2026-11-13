# Gate B 最终授权审阅清单（未授权）

READY_FOR_GATE_B_AUTHORIZATION_REVIEW；GATE_B_APPROVED: **false**。这是供下一次明确决策的具体清单，本次到 Gate A 结束。Dashboard 核验与本地测试不构成远程执行授权。Manifest 为机器可读清单；历史窗口已撤回，不自动顺延。

## 资源、范围和代码

一个 Worker `us-stocks-p51b-mock-20261113`；一个 SQLite class/namespace `RemoteMockCoordinator`；一个命名实例 `phase51b-synthetic-20261113-v1`；绑定 `COORDINATOR` 指回同一 Worker/class。资源名保留创建提案日期，不随实验日期改名。实际 namespace/DO ID、账户脱敏引用、workers.dev URL 未来核对并留在本项目受控记录；不保存完整账户 ID。不得覆盖已有同名资源。

同一 Worker 临时 HTTPS 桥五条固定管理路径；三个独立 Secrets `MOCK_INIT_TOKEN`、`MOCK_CONTROL_TOKEN`、`REPORT_TOKEN`；最大两次显式代码部署。不创建第二管理 Worker、Cron、R2、routes/custom domain、生产状态导入或 Yahoo 请求，不升级付费。默认配置仍是 `DISABLED_PENDING_GATE_B`，H01 flag/目标 ID/Secret 均未配置。默认 build 仍是本地 PoC，禁止当成远程 Mock 包。

源码与实际 remote bundle 的哈希见 `reviewed_code_sha256.json`、`remote_build_audit.json` 及 Manifest；执行前必须核对相同 bundle 和差异。任何新增代码、资源、权限或未列部署效果均停止并重新审阅。

## 候选时间及两个显式阶段

| 阶段 | Brisbane (UTC+10) | UTC / 约束 |
|---|---|---|
| 人工账户/权限准备和第一次部署 | 11-16 07:30–08:00 | 11-15 21:30–22:00；先配 control/report Secrets，H01 flag 与 init Secret 缺席 |
| Stage 1 身份核验 | 11-16 08:00–08:15 | 11-15 22:00–22:15；仅固定实例 identity，必须 empty_sql/native、Alarm=null |
| 第二次部署及 Secret 就绪 | 11-16 08:15–08:45 | 11-15 22:15–22:45；相同代码，绑定精确 ID、最终窗口和 H01 flag；配置 init Secret |
| 最终实验及初始化 | 11-16 09:00–09:20 | 11-15 23:00–23:20；部署/身份/Secrets 已完成后才 initialize；初始化只允许这 20min |
| 两轮 Mock 与监督 | 11-16 09:20–10:00 | 11-15 23:20–11-16 00:00；fixture 固定 11-06、11-09，依次运行；正常预期各约数分钟，不保证平台延迟 |
| 指标、停止与撤销 | 11-16 10:00–10:30 优先完成 | 11-16 00:00–00:30；不要等满24h；保存指标、STOPPED、Alarm=null、撤销并验证 |
| 硬截止 | 11-17 09:00 | 11-16 23:00；24h end exclusive；此后不能采集 |
| control stop/status 宽限截止 | 11-17 10:00 | 11-17 00:00；只用于停止/核验，不延长实验 |

**20 分钟不应承担完整部署流程，无法保证两次远程部署都在其中完成。** 当前 identity 入口本身要求处于配置时间内，因此 Stage 1 需使用单独的、尚未持久化的准备窗口：start `2026-11-15T22:00:00Z`、end `2026-11-16T22:00:00Z`、initEnd `2026-11-15T22:20:00Z`，且 H01 禁用、init Secret 缺席，绝不 initialize/start。它只开放受鉴权的身份核验，未初始化时任何 start 均失败。

第二次部署在 08:45 前将同一 Worker 切换到仓库当前候选最终窗口 `23:00Z → 次日23:00Z`，initEnd `23:20Z`，并绑定刚读取的精确对象 ID。这一变化只发生在任何持久化初始化之前，不延长已持久化截止时间；若发现 receipt/状态/Alarm，停止并人工核对，不能删除重建。最终窗口与实际云端两阶段配置均须在 Gate B 明确批准后逐一核对，当前两阶段都未部署。Stage 1 的准备绑定已落实为仓库 `p51b-identity-prep` 模式，与 `p51b-mock` 最终模式均本地 dry-run 及审计通过，两个模式仍为 DISABLED_PENDING_GATE_B。准备模式的配置与 bundle hash 见 preparation_build_audit.json。未来开启/绑定实际目标 ID 或 Secrets 后仍须比对获批差异及重建配置审计，不能只编辑 Manifest。

若第二阶段或 Secrets 未在 08:45 准备好，不启动初始化；若 09:20 尚未完成，终止该尝试，保留现场与证据、撤销能力，另行提出新窗口和审阅，不能第三次部署补救或就地延长期限。成功初始化后不再修改窗口。窗口包含夜间仅作为硬上限，不依赖通宵人工监督；计划当天上午完成安全停止。

## 必须单独确认的授权项

1. 选择用户核验的目标账户，执行前重查 Free、唯一候选名、既有 workers.dev、共享用量及 namespace，记录精确时间/时区；不得访问其他项目代码/Secret 或调用其 Worker URL。
2. 接受上列隔离资源、公开 HTTPS 入口、固定 ID、三份随机 Secrets、两次部署及 Secret/绑定变更可能额外产生版本的风险。若操作需要额外代码部署则停止；不默许第三次。
3. 决定 bootstrap 认证路径。推荐用户用既有 Dashboard 权限亲自完成第一次部署，后续使用单 Worker Editor Token；Beta cf 新权限兼容性未验证。代理 cf bootstrap 需账户 Workers 产品级 Admin，可影响其他 Workers，必须额外明确批准，不能自动退回此方案。完整权限、位置、撤销及替代见 `gate_b_authentication_plan.md`。
4. 批准两个配置窗口及最终24h/20min限制；预算2 runs、24 collector attempts、80 processed Alarm ticks、主动管理/报告≤200。平台重复投递及公开无效请求另计，应用预算不能当成账户账单硬封顶。
5. 批准数据面 initialize/start/stop 及撤销，真实 CPU、Duration、Alarm/SQL 指标为 PENDING_REMOTE_TEST；保存原始状态，不自动修复异常、删除或重建。Secret 撤销不需要第三次显式代码部署；若 flag 撤销要求第三次部署，保留已过期 flag，通过移除 init Secret、不可重放 receipt 及 initEnd 共同失效，记录保留状态，不超出部署上限。
6. 默认 `STOP_REVOKE_AND_RETAIN`：持久化 STOPPED、取消目标 Alarm、导出合成证据/指标、撤销三个 Secrets 和临时控制面凭据；保留 Worker/namespace/存储。HTTP init flag 若能在既定变更内关闭则关闭，否则按第5项 fail closed；不假称 flag 已删除。
7. 费用只作条件预计 US$0：用户报告 Workers Free，官方 SQLite Free 权益；共享配额和真实计量不能保证。Workers 已用量未提供，DO 数值缺少精确图表窗口。执行前再核实；任何升级、未知费用、1102或额度错误即停止，不付费、不提额。

## 可选清理：FULL_CLEANUP_AFTER_REVIEW

本次及默认 Gate B 均不删除云资源。日后用户单独批准后：核对测试账户/Worker/namespace/对象 ID → STOPPED 与 Alarm=null → 导出并校验报告、receipt、SQL/运行记录及哈希 → 确认没有其他 Worker 绑定该 namespace → 仅对该测试 namespace 制定官方支持的 class 删除/migration/存储删除步骤并复核权限 → 执行批准的精确删除与 Worker 删除 → 查询 namespace/Worker 列表确认，无残留后撤销删除凭据。不能假设删除 Worker 已删除 DO 持久化数据；SQLite 数据删除不可恢复，只能依靠事先导出证据，不能保证可还原运行。该方案可能需要额外部署、Admin 权限和不可逆删除，必须另批，不属于两次实验部署额度内动作。

当前执行阻断明确保留：Gate B 未批准；账户/URL/ID 最终选择与临近用量需复核；bootstrap 权限决策未作出；cf 与单 Worker Token 的兼容性尚未实证；云端资源/指标尚未创建验证。这些不是本地 Gate A 测试失败，也绝不是现在可以部署的依据。
