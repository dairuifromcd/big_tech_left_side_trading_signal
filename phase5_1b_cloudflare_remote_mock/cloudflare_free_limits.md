# 免费额度核对

查询日期：2026-11-12 UTC。下列均为 **DOCS_ONLY_VERIFIED**，不代表本账户权益或余额。

| Workers Free | 文档值 |
| --- | --- |
| 请求 | 100,000/UTC 日，账户共享 |
| HTTP / Cron CPU | 10ms/次 |
| isolate 内存 | 128MB |
| 子请求 / 并发外连 | 50/请求；6/请求 |
| Worker / Cron 数量 | 100/账户；5/账户 |
| 静态资源 | 20,000 文件/版本，25MiB/文件；本实验不使用 |
| CPU 超限 | 可出现 1102 / exceededCpu |

来源：[Workers limits](https://developers.cloudflare.com/workers/platform/limits/)。Worker 转发成本也必须云端测量。

| SQLite Durable Objects Free | 文档值 |
| --- | --- |
| 可用后端 | SQLite；不使用旧 KV 后端 |
| 请求（RPC session、Alarm 等） | 100,000/UTC 日 |
| Duration | 13,000 GB-s/UTC 日 |
| SQL rows read / written | 5,000,000 / 100,000 每日 |
| SQL 总存储 | 5GB/账户 |
| Alarm storage | 每次 setAlarm 计一次 row written；删除也有写入计量 |
| Free 超额 | 对应操作失败；每日额度 00:00 UTC 重置 |

来源：[DO pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/)。计量包含索引/触发器、内部存储，不能用业务行数代替账单。

DO 默认 CPU 30s，可配置最高 5min；本实验不增加 CPU 配置。Alarm wall time 15min。类数量 Free 100；SQL row/value 8MB、statement 100KB、绑定参数 100。来源：[DO limits](https://developers.cloudflare.com/durable-objects/platform/limits/)。

文档冲突：limits 表写每对象 10GB，同页 FAQ 写 Free 1GB；采取保守 **1GB/对象**，待账户核实。Alarm 页仍称每 Worker 3 Cron，与 Workers limits 的账户 5 个口径不一致；本实验创建 **0 Cron**，不据此选宽松值。

每 DO 同时一个 Alarm；至少一次交付。异常抛出触发从 2s 开始的指数退避，最多 6 次重试。来源：[Alarms](https://developers.cloudflare.com/durable-objects/api/alarms/)。

`cf deploy` 可自动 provision 缺失资源；dry-run 不发 API、无需凭据，但会本地构建；无配置时甚至可能自动安装和改配置。本项目已有配置，锁定 Beta 与现有依赖，使用 `--dry-run --provision=false`。来源：[cf projects](https://developers.cloudflare.com/cf/projects/)。不能从 dry-run 推断账户无冲突或部署成功。
