# 下一阶段最小真实Cloudflare PoC

READY_FOR_CLOUD_POC: CONDITIONAL_MOCK_ONLY

本阶段到此停止。以下全部远程写入均为REQUIRES_SEPARATE_AUTHORIZATION；不是本次授权的延续。

1. 在具有Cloudflare插件的会话中完成只读套餐/资源/额度/命名冲突核实；不导出ID/Secrets。确认DO Free存储文档矛盾、报警与超限机制。
2. 先补齐旧状态导入、原字节证据封装、受信归档应用/恢复验收、真正SQL分页与独立备份设计；如仅测试Mock运行时，可使用全新隔离Mock baseline，不接入正式历史。
3. 申请创建一个专用测试Worker、一个SQLite DO namespace/class及仅测试对象；配置独立鉴权secret或Access策略，上传一次测试版本。不得绑定生产域名或导入其他项目数据。
4. 首轮只允许Mock：手动调用、重复触发、Alarm、重启、SQLite事务和有限执行次数；记录真实CPU、duration、SQL rows、存储增长、Error1102和权限隔离。完成后人工决定保留/删除测试资源，所有清理写入也需纳入授权。
5. Cron先不开。确认安全后，另授权一个有截止日期/次数的Cron试验；保持UTC候选，不恢复Phase4已停止任务。
6. 真实Yahoo出口测试另授权：明确每symbol请求数、单次声明、≥5秒间隔、每批额外30秒、429/401/403停机、无未知结果重试。不能自动从Mock阶段进入真实采集。
7. R2开通、Bucket、独立备份、付费方案均单独审批；不把插件OAuth等同于写权限。

预期Mock小流量在Free余量充足时有望US$0；这是估算，账户/账单未核实。Paid/Containers至少涉及US$5/月订阅及额外资源；R2超免费额度计费。申请授权时应列资源名、次数、费用上限、停止条件、项目外影响、恢复与清理方法。不得在尚未获得授权时执行。

只有真实环境才能确认：账户产品可用性、实际资源余量、Free CPU/内存、出站限制、Alarm时延/重试/故障迁移、长期Cron可靠性、SQLite配额/灾备、Yahoo云端可达性/发布时间/23-5口径。所有这些状态继续NOT_VERIFIED。
