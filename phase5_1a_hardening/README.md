# Phase 5.1A 本地验收复现

所有输出必须写本阶段目录，不能重写 Phase 5.1 历史验收。没有部署或Git写入命令。

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/cloudflare/.tmp" .venv/bin/python cloudflare/scripts/hardening_audit.py python
node cloudflare/scripts/local.mjs typecheck
node cloudflare/scripts/local.mjs offline phase5_1a_hardening
node cloudflare/scripts/local.mjs test phase5_1a_hardening
node cloudflare/scripts/local.mjs initialize-local
node cloudflare/scripts/local.mjs build
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python cloudflare/scripts/hardening_audit.py verify
```

`test`、`initialize-local`、`build`需要环境允许临时loopback监听。在受限沙箱失败后申请了相应本地运行授权。包装器使用项目内锁定Node，清空继承的云端credential，禁用telemetry；缓存、临时文件均在cloudflare内。Miniflare出站被拒绝。不要开启SQL检查器进行初始化演练，因为它会先写模拟器元数据表。

baseline.json只能创建一次；不要重建它来掩盖差异。原tracked文件中仅7个H01/H02相关文件允许变化，其他500个文件应保持hash一致。新的源码、测试和本阶段文档另外列入交付清单。

完整TS结果以typescript_tests.log为准；offline_tests.log是无workerd的子集。原Python、Golden输入、32个Yahoo验证fixture没有修改，旧135项TS测试全部保留。
