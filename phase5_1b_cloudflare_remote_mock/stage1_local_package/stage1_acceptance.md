# Stage 1 本地部署包验收

PHASE_5_1B_STAGE1_LOCAL_PACKAGE: **PASS**（仅本地准备，2026-11-13 Australia/Brisbane）。
Git HEAD `4651ca01f2514b0e6be07578de1bdf7bec5bc06a`；无提交、推送、登录、远程部署或云资源创建。原Manifest与9份研究文件均保持原字节。

| 分项 | 结果 |
|---|---|
| `DEFAULT_BUILD_DISABLED` | PASS_LOCAL_ONLY |
| `STAGE1_IDENTITY_ENABLED` | PASS_LOCAL_ONLY |
| `H01_INITIALIZATION_DISABLED` | PASS_LOCAL_ONLY |
| `MOCK_START_DISABLED_BEFORE_INITIALIZATION` | PASS_LOCAL_ONLY |
| `UNAUTHORIZED_REQUESTS_REFUSED` | PASS_LOCAL_ONLY |
| `EMPTY_SQL_AND_NATIVE_STORAGE` | PASS_LOCAL_ONLY |
| `ALARM_NULL` | PASS_LOCAL_ONLY |
| `NO_EXTERNAL_COLLECTOR` | PASS_LOCAL_ONLY |
| `WORKERD_SQLITE_TESTS` | PASS_LOCAL_ONLY |
| `TYPESCRIPT_REGRESSION` | PASS_LOCAL_ONLY |
| `GOLDEN_PARITY` | PASS_LOCAL_ONLY |
| `PROTECTED_FILES_INTEGRITY` | PASS_LOCAL_ONLY |
| `BUILD_OUTPUT_AUDIT` | PASS_LOCAL_ONLY |
| `DEPLOYMENT_RUNBOOK_READY` | PASS_LOCAL_ONLY |

完整TS380/380（285原有+95新增；零跳过/取消/TODO），typecheck通过。Stage1 Node51、观测型workerd42；另用实际cf产物workerd42项检查（独立运行含父测试43/43）。H01/H02、事务原子性19个workerd场景、两种状态的Node/workerd重复启动、Golden76+32验证/11145数值字段最大差异0均通过。Python未修改，沿用已验收271/271。初次沙箱监听失败和测试适配失败日志保留，最终全通过。

workerd执行真实Bundle与SQLite，但在本地进程注入虚构Control/Report及相对当前时钟的三项窗口绑定；没有等待真实候选日期或修改主机时钟。候选配置的三个固定UTC文本单独静态审计，Node注入时钟验证精确边界。此模拟不证明候选时刻云端行为。

Identity每次检查SQL/native为空、Alarm=null、initialized=false；Node记录0条写入/事务/sync/Alarm变更，workerd观察schema=[]/total_changes=0/native=[]/collector=0。无应用schema即无Receipt、Run、Claims和STOPPED记录。Stage1所有非Identity HTTP/RPC在状态访问前拒绝；原H01代码及开关规则未削弱。

完整cf Build Output：`phase5_1b_cloudflare_remote_mock/stage1_local_package/builds/stage1/.cloudflare/output/v0`，5个文件（含隐藏`.vite/manifest.json`、source map、root config、worker config与JS）。不是单独esbuild Bundle。源图仅13个合成/规则模块（JSON不出现在Vite source map），没有本地RPC、生产状态、Yahoo网络采集器或凭据。默认包与原验收Bundle哈希完全相同。

| 哈希对象 | SHA-256 |
|---|---|
| 当前源/配置/测试/脚本聚合 | `16a4048c783ef39a30e85842be29f5a3f44905b71bb22bb8a10bc1f1fd3b4e41` |
| Stage1 JS（156651 bytes） | `f750138982c60fdca94c47fea14a5d93c47d03a0daeb154795c0a1a275caf7a6` |
| Worker配置 | `bfca973a1f48aefc457fe27e7685ee110e8b10985997d25421279d3ced9712c4` |
| 完整Build Output清单聚合 | `9d905d8da36bf5602dadbda25280d0fc4504d7a9b73d06dfc5cbb1bfd654ed39` |
| 依赖锁 | `dcb23a1554ad5cb2ecc3f1a3970e8bccbcc25d60be104eb513bf940698d8c599` |
| 原Manifest（未改） | `29adb600b8a79d4648aa6699f898011d77ae1cfcb2615ca2fe33944f668754d7` |
| Stage1 package_manifest.json | `bd9b7a0ab0aab64ea36476c574747052e24919f12b2e8f4c3696b701e7ae7a7c` |
| 测试证据清单聚合 | `a6f263dbbd1c8527417df0b552cc5ec09311425709d1613cb7a6e9d709356f0a` |

聚合算法是排序路径→文件SHA256映射的紧凑JSON再SHA256；单文件完整清单见各output_inventory.json、source_sha256.json及stage1_build_audit.json。release_inventory.json记录最终交付文件及代码的逐文件哈希，不自我包含。未来使用`check-release`只读核验，不运行会刷新hash的`verify`来代替审批。

本地PASS不证明实际账户权限、SQLite首创、Secret激活、URL传播或计费成功。建议提交**仅用户人工首次部署**的单独授权审阅；不建议现在执行。不足以在候选窗口前完成授权/核验就推迟，不自动扩窗。

```text
CLOUDFLARE_REMOTE_MUTATIONS: 0
REMOTE_DEPLOYMENTS: 0
OAUTH_LOGINS: 0
API_TOKENS_CREATED: 0
REAL_SECRETS_CREATED: 0
SECRETS_UPLOADED: 0
REAL_YAHOO_REQUESTS: 0
LIVE_TRADING_ACTIONS: 0
GATE_B_APPROVED: false
```
