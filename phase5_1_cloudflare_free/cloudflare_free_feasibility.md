# 免费方案可行性

CLOUDFLARE_FREE_ARCHITECTURE: CONDITIONAL

以下是2026-11-11查阅的官方文档限制，不能当作本账户已核实额度。

| 项目 | 官方公开限制 / 风险 |
|---|---|
| Workers Free请求 | 100,000/日；账户共享，UTC零点重置 |
| 普通Worker HTTP/Cron CPU | 10ms/调用；不能套用于DO |
| 内存 | 每isolate 128MB；共享并发请求，非每请求独享 |
| Free子请求 / 并发外连 | 50/调用 / 6；本架构每Alarm最多一次Yahoo请求 |
| Cron | Free每账户5个；本项目设计只需1个 |
| Static Assets | Free每版本20,000文件，单文件25MiB |
| DO CPU | 默认30秒；文档描述可配置至5分钟，本阶段不依赖提额 |
| SQLite DO | Free可用；Free不能使用legacy KV-backed DO |
| DO请求 / duration | 100,000/日 / 13,000 GB-s/日；Alarm也计请求 |
| DO SQL | 5,000,000 rows read/日、100,000 rows written/日、账户5GB |
| SQL单行/字符串 | 当前文档8MB；本实现进一步保守限制原始封装1MB，超过阻断，未实现分块 |
| SQLite事务 | transactionSync同步回调，异常回滚；禁止SQL BEGIN，不能事务内await |
| Alarm | 每DO一个；至少一次投递，异常指数退避，从2秒开始、最多6次重试 |
| 超限 | Free相关操作报错/请求拒绝；不能假定会自动转付费或自动恢复 |

来源：[Workers limits](https://developers.cloudflare.com/workers/platform/limits/)、[DO limits](https://developers.cloudflare.com/durable-objects/platform/limits/)、[DO pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/)、[SQLite API](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/)、[Alarms](https://developers.cloudflare.com/durable-objects/api/alarms/)。

DO limits页存在内部不一致：上方表格写单DO 10GB，SQLITE_FULL说明仍写Free单DO 1GB；账户5GB一致。设计暂按单DO 1GB预警/预算，不能据此承诺10GB。需Cloudflare官方澄清及真实账户测试。免费额度是账户级资源预算，其他项目占用未知，不能将所有公开额度分配给本项目。

静态资源本身请求免费且不限量、存储无额外费用；API或run_worker_first仍计Worker请求，超额可能429。[Static Assets billing](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/)。未来React SPA适合Static Assets，Phase5.1未创建资源或开发页面。

R2可归档原始响应、快照和审计，减轻DO存储增长；Standard免费10GB-month、每月1M Class A和10M Class B，互联网egress免费。超出含量会计费，Infrequent Access不适用该free tier。需要R2 subscription与checkout，不能把“免费额度”当无账单风险。[R2 pricing](https://developers.cloudflare.com/r2/pricing/)、[R2 signup](https://developers.cloudflare.com/r2/get-started/)。本账户是否已开通未知；本阶段未开通。

付费备用：Workers Paid最低US$5/月；Containers需Paid并另计CPU/内存/磁盘，适合避免大规模Python移植或依赖原生包时。容器本地磁盘不能默认作永久状态；仍需可靠状态/备份与采集声明。[Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/)。

VPS备用：保留Python的改造成本较低，可使用SQLite/定时器；需自行处理系统补丁、TLS、备份、磁盘和进程监控。官方入门报价可低至US$4/月，备份/税/带宽等另核算。[DigitalOcean pricing](https://www.digitalocean.com/pricing/droplets)。不是本阶段的部署或采购建议。

结论：小规模日线计算有免费架构依据；永久保留全部原始证据且无限运行，不可能仅凭有限免费容量得到无条件US$0保证。不能删证据来维持免费。资源增长、独立备份、账户余量和云端CPU/Yahoo可达性仍是实际可用性的门槛。
