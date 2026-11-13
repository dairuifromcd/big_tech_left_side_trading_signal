# Finalization 窗口更新

以下旧窗口为历史方案，已撤回。当前准备/最终模式均禁用；初始化仅在最终候选Brisbane2026-11-16 09:00–09:20（UTC11-15 23:00–23:20），实验硬截止11-17 09:00 Brisbane，control宽限至10:00。两个显式部署和Secrets应在初始化窗口前完成；Stage1未初始化准备窗口的身份核验、Stage2切换及超时停止规则见gate_b_authorization_request.md。Gate B未获授权。

---

# 远程初始化安全设计

REMOTE_INIT_SECURITY_READY: LOCAL_PASS。真实 Cloudflare 初始化 NOT_VERIFIED，Gate B 仍被账户/认证/授权条件阻断。

当前实现提供临时 HTTPS 管理桥 → 固定本 Worker DO 内部 RPC。不是 Dashboard 初始化路由。桥没有通用 RPC、URL、SQL、测试时钟、故障或删除状态入口。`LOCAL_TESTING` 不存在于远程入口和配置。

身份验证：三份互相独立、随机至少 32 字符的 Secret。`MOCK_INIT_TOKEN` 仅初始化；`MOCK_CONTROL_TOKEN` 仅 identity/status/start/stop；`REPORT_TOKEN` 仅六类 GET 报告。SHA-256 后恒定时间比较，失败响应不回显凭据。不启用 CORS，不接受 query token；POST body 实际流式计数最多 4096 bytes。

H01 保留显式 enable、精确 env Object ID == ctx.id == command target、完整六字段 command、空 SQL schema/原生 KV/Alarm、原子 Receipt 和审计、拒绝重复初始化。新增 trusted bootstrap callback 仅在 Store 初始化事务内创建预算，callback 不通过 RPC 暴露；预算失败时 Receipt/schema 同时回滚。

候选 Gate B 操作顺序（尚未执行）：

1. 账户、名称、URL、权限与窗口获批后，部署版本 1：专用类、固定实例、控制/报告 Secret，临时桥启用但 H01 初始化 flag 缺失。
2. 鉴权 identity 只读确认实例 ID、空数据库/原生存储/Alarm。不能删除残留再试。
3. 部署版本 2：同一 Worker/类，绑定精确 ID、H01 flag 和初始化 Secret。重新 dry-run/比对资源，禁止改业务代码。
4. 在 20min 初始化窗口内发送一次完整命令。Receipt 时间是真实 UTC；初始化与预算持久化原子提交。若响应不确定，只读核对 Receipt/状态，不重试、不删除重建。
5. 验证重复请求被拒绝；删除初始化 Secret、停用初始化 flag。Secret 删除/绑定修改是另需纳入批准的远程写入，可能改变活动版本，必须记录。
6. 运行结束后 stop → 验证 Alarm=null、持久化 STOPPED → 导出脱敏证据 → 撤销控制/报告 Secret。

初始化限于 2026-11-14 00:00–00:20 UTC；采集窗口截止 2026-11-15 00:00 UTC。控制 start 受持久化窗口/预算约束；stop/status 可在截止后额外 1h 内完成应急核验，01:00 UTC 后控制 Secret 即使未删除也不能使用。报告只读 Secret 由授权清理撤销。

公开 URL 即使鉴权拒绝也会消耗 Worker 请求额度；凭据被持有者可在时效内耗尽本实验有限预算。此风险及临时入口必须明确批准；不能声称 Service Binding 本身使外层 HTTPS 私有。需要 Access/额外域名或更广权限时，停止并重新申请，不能顺带创建。
