# Cloudflare Phase 5.1 — 本地离线 PoC

仅 DRY_RUN / Mock Yahoo。Python reference、正式状态与旧验收目录均未修改。
没有真实 Yahoo transport，没有部署脚本，没有 Cron 配置，没有账户 ID 或凭据。

从项目根目录运行：

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/cloudflare/.tmp" .venv/bin/python cloudflare/scripts/audit.py test
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python cloudflare/scripts/golden.py
node cloudflare/scripts/local.mjs typecheck
node cloudflare/scripts/local.mjs offline
node cloudflare/scripts/local.mjs build
node cloudflare/scripts/local.mjs test
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python cloudflare/scripts/audit.py verify
```

`local.mjs` 使用锁定在项目中的 Node 22，清空继承凭据，禁用 CLI telemetry，
将缓存和临时目录放在本项目。build/test 的 workerd 本地监听需要运行环境允许 loopback。
不运行 `cf init`、登录、deploy、远程 bindings 或账户查询。

依赖已用 exact versions 和 package-lock.json 锁定。首次重装须把 npm cache、
userconfig、globalconfig 都指定到 `.cache`；不要全局安装或使用默认用户缓存。
本地 cf 采用唯一 `cloudflare.config.ts`，无 Wrangler 配置。Miniflare 5 的测试配置
只描述本地实例与测试 bindings，不是另一套部署配置。

纯模块依赖顺序：core/calendar → yahoo → observations → storage → coordinator → api/worker。
`fixtures/golden.json` 是原 Python 输出，不是从 TypeScript 生成的期望值。
`fixtures/legacy-pending.json` 仅为隔离测试副本，不用于替代正式事件。

验收范围、尚缺功能、资源限制及下一阶段权限见 `../phase5_1_cloudflare_free/acceptance.md`。
当前实现不可直接接入真实 Yahoo 或正式历史状态；完整端到端移植尚未验收。

## Phase 5.1B Gate A

隔离远程 Mock 的候选配置使用 `--mode p51b-mock`，当前默认关闭。只进行本地预览：

```sh
node cloudflare/scripts/local.mjs remote-dry-run
```

此命令清空继承认证环境，执行 `cf deploy --dry-run --provision=false`，不部署。
远程入口只依赖合成行情，不打包 `fixtures/samples.json`；本地 Golden 仍使用原样本。
远程窗口、初始化对象 ID、管理桥、Secrets 和账户都必须在 Gate B 单独获批后配置。
查看 `phase5_1b_cloudflare_remote_mock/gate_a_acceptance.md` 和 `deployment_manifest.json`。
本阶段不自动提交或推送 Git。
