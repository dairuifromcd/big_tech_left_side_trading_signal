# Stage 1 实际可达路径与安全矩阵

证据：stage1_node_results.json（51 checks）、stage1_workerd_results.json（42 checks）、stage1_full_output_workerd_results.json（实际cf Bundle42 checks），完整TS日志。所有测试凭据使用测试进程randomBytes，既不记录值，也不进入源码常量、Manifest或部署Bundle；没有真实Secret。

| 路径 / 能力 | Stage1实际行为 | 拒绝与无副作用证据 |
|---|---|---|
| GET /_mock/identity | 只有专用Control Bearer、合法窗口、无query返回200 | 固定getByName；initialized=false、empty_sql/native=true、Alarm=null |
| Identity缺失/错误/Bearer格式错误/Report冒充Control | 403通用错误 | HTTP逐一测试；不创建表或Alarm |
| 配置缺失/过短Control | 403；直接RPC拒绝 | Node及workerd；不生成新凭据 |
| 默认、既有prep、Stage2禁用模式 / 未知enable | Identity不可用 | 构建配置精确审计，Node禁用值和workerd禁用模式测试 |
| Identity对象ID、namespace、SQL、fixture、token query | 403 | 不选择任意对象、不执行query SQL；Node路由桩断言固定名称 |
| POST Identity | 405 | 无写入 |
| POST /_mock/initialize | 403；直接RPC STAGE1_IDENTITY_ONLY | 即使误注入完整H01字段也拒绝；正式包3项H01绑定均缺席 |
| POST /_mock/start，固定或任意fixture | 403；直接RPC拒绝 | 无Run/Claims/预算/任务/Alarm；不接受任意日期 |
| POST /_mock/stop | 403；直接RPC拒绝 | 不伪造STOPPED，不执行sync/deleteAlarm |
| GET /_mock/status | 403；直接RPC拒绝 | 不读取/泄露实验、Receipt或数据；不创建schema |
| 六类GET /api/*报告 | 正确Report仍403；无/错Report401 | Stage1禁用report RPC，API数据不可达 |
| POST /api/* | 有效Report405；无有效凭据401 | 不执行API写入 |
| 未知管理、对象路径、SQL入口 | 403 | 没有任意SQL/本地测试RPC；workerd缺失方法实际拒绝 |
| Direct RPC identity | 同样Control和时间守卫 | HTTP不能提供其他DO/namespace；绑定属于固定Worker |
| Alarm callback | Stage1立即返回 | Node调用真实alarm()确认零状态/Alarm操作；无HTTP Alarm入口 |
| 真实Yahoo / 交易 / 正式监控 | 不可达 | Stage1只读；合成collector calls=0，outbound=0；远程源图无网络collector |

Node精确时钟验证start-1拒绝、start允许、initEnd后仍可Identity、end-1允许、end及以后拒绝；Stage1没有Stage2的额外1h控制宽限。workerd通过配置窗口重载验证开始前及结束后拒绝，再回到原窗口读空状态。重复Identity、DO适配器替换和workerd进程dispose/recreate后ID不变、空状态不变。workerd模拟重启不等于真实云端eviction。

Node将所有非SELECT SQL、事务、sync、set/deleteAlarm计为mutations；所有检查后均0。workerd本地专用观察类检查全部应用sqlite_master、total_changes()、native和Alarm；它只存在于内存测试构建，未进入cf产物。实际cf Bundle另行执行同一HTTP/RPC拒绝与身份/重启检查，部署包没有观察RPC。内部SQL查询是固定代码，不接受HTTP SQL字符串。

Stage1是显式能力限制；Stage2仍使用原EXPLICIT_PHASE51B_MOCK_V1并保留原H01+Receipt+checkpoint+持久化窗口守卫，原回归全通过。默认src/worker.ts及Python策略不变。
