# 剩余风险与未验证事项

本地包PASS，远程执行未授权；没有新开展大范围部署研究，依据已有9份研究与锁定本地cf源码/实际构建验证。

| 未决事项 | 当前边界 / 后续停止条件 |
|---|---|
| 首次Workers Admin授权范围 | 尚不存在的Worker不能按名称限制Admin；只由用户持有、短TTL并立即服务端撤销 |
| beta29真实SQLite exports首创 | 本地声明/Miniflare SQLite通过；--provision=false下真实平台协调仍NOT_VERIFIED，失败停止，不补migration/扩权 |
| 实际账户/Free/额度 | 无账户API调用；历史Dashboard报告不能代表临近余额，无零费用保证；收费/升级提示停止 |
| workers.dev与previewUrls默认 | 包保持既有未显式配置；可能写目标Worker默认设置，须用户确认已有子域和接受精确效果；不能自动注册账户子域 |
| 名称首次创建竞态 | 无已证明原子create-only flag；部署前人工再查，同名即停止 |
| Secret上传、Version与激活/撤销 | 生成版本不保证切换流量；逐次核验活动版本，任何额外激活另批；不能把省略键当撤销 |
| 单Worker Editor整条CLI依赖 | 尚未端到端实证；额外权限403即停止，不扩权或将Admin交代理 |
| ID/namespace跨Stage2稳定性 | 本地重启一致；云端必须相同账户/Worker/class/namespace/固定名实证。测试ID绝不用于云端 |
| 同OS用户凭据隔离 | 用户独立Terminal是操作边界，非硬隔离；不让Codex接触值，服务端撤销；更强隔离另批 |
| 真实CPU/Alarm/SQL/计费 | 本地workerd不能证明云端Free CPU或配额；Stage1没有应用Alarm，未测实际Alarm服务 |
| 候选时间可行性 | Brisbane11-16 08:00–08:15核验；准备/授权不充分就推迟，不自动扩窗；Stage1 Identity硬截止11-17 08:00，无额外宽限 |
| Stage2独立批准 | Stage1不能initialize/start/stop/status/report；现有Stage2仍禁用，必须另审精确ID/H01/Secrets/完整包与Gate B |

Stage1模式刻意在HTTP及RPC双层拒绝副作用，即使有人误注入H01字段仍不启用。所有远程源码包含Stage2内部规则实现，但没有本地测试RPC或任意SQL入口。默认生产入口与Python未改变，原安全机制没有通过禁用来让测试通过。

建议：本包可提交“用户人工首次部署”的独立授权审阅，先解决账户、TTL、默认URL效果、Secrets激活/撤销和一次尝试账本；这不是授权，也不是云端可行性保证。若来不及完成，推迟候选实验。
