# 配置精确差异与Bundle重新验收

唯一启用方式：本地显式`node cloudflare/scripts/local.mjs stage1-build`（内部cf build --mode p51b-stage1）。不能把现有p51b-identity-prep当启用包。没有凭据仍拒绝Identity。

| 字段 | 原禁用prep / 当前disabled_preparation | Stage1 |
|---|---|---|
| mode（root buildContext） | p51b-identity-prep | p51b-stage1 |
| env.REMOTE_MOCK_ENABLED.value | DISABLED_PENDING_GATE_B | EXPLICIT_PHASE51B_IDENTITY_V1 |
| entrypoint | src/remote-worker.ts | 相同 |
| Worker | us-stocks-p51b-mock-20261113 | 相同 |
| export / storage | RemoteMockCoordinator / sqlite | 相同 |
| COORDINATOR | 同Worker/exportName | 相同 |
| start / end / initEnd | 11-15 22:00 / 11-16 22:00 / 11-15 22:20 UTC | 相同 |
| compatibilityDate / flags | 2026-11-10 / nodejs_compat | 相同 |
| H01 flag / ID / init Secret | 缺席 | 缺席 |
| Control / Report Secret | 构建中缺席 | 构建中缺席；未来用户独立配置 |
| Cron/R2/Routes/Custom Domain/额外Worker或class | 无 | 无 |
| workersDev / previewUrls | 未显式指定 | 同样未指定；默认效果须用户未来审阅 |

程序逐字段断言Worker配置仅一个env值不同，两个root config只有mode不同；当前两个remote禁用模式和Stage1的JS字节完全相同。Stage1与disabled Stage2配置还相差三项时间（Stage2仍23:00/23:00/23:20），没有自动将Stage2启用。

相对历史HEAD远程Bundle由156016变为156651 bytes；旧hash `4dd23002f2548f7d29035fdfa10d5e26cf3e5a1c7769786bac88ab6671da8976`，新hash `f750138982c60fdca94c47fea14a5d93c47d03a0daeb154795c0a1a275caf7a6`。原因是加入identity专用enable值、HTTP/RPC副作用拒绝、Stage1精确截止与Identity query拒绝。重新通过380/380及实际cf Bundle workerd42项检查，未沿用旧hash。Stage2完整enable值/H01/持久化设计不变；Stage2也会包含这些已验收守卫代码。

默认production包仍使用src/worker.ts，没有remote enable/init/test/report Secret绑定；Bundle hash仍为历史`4fa3f652a0a585c21885ea6a6422f58f4b0de6971f21c01604be4c7b566b2f49`。正式执行入口和Python市场逻辑未改。

四种模式的完整输出各自留存在builds/下，源目录最后活动输出为Stage1。用户未来从builds/stage1执行--prebuilt，避免其他mode构建覆盖共用活动目录；该独立目录已完成无凭据dry-run。
