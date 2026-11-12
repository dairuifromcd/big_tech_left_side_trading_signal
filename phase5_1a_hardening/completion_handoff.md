PHASE_5_1A_HARDENING: PASS

Git HEAD: a324465ee094dbf733acabe9e142251a3841ab79；初始干净，当前仅有H01/H02相关未提交改动。

修改：storage/coordinator/worker/core的相关逻辑、测试输出位置和本地runner；新增checkpoint/initialization/integrity模块、初始化工具、安全测试及本阶段文档。完整文件清单见acceptance.json。

H01：默认关闭的内部初始化RPC；独立credential、目标ID与授权说明；严格新空库，事务写入可验证receipt/schema/audit。无Dashboard管理路由，不启用通用测试后门。

H02：完整checkpoint只读验证与启动同一事务；状态/事件/evidence/audit/跨引用/原始证据一致性；请求前generation复核；单标的提交保护旧决定和依赖标记。

新增安全测试68项，完整TS 203/203；Python 271/271；无失败/跳过。

Golden76 + Yahoo32，11145个数值字段最大差异0，ID及离散结果一致。

保护：500个受保护tracked文件不变，Phase5.1资料未覆盖，7条旧pending不变。

未验证：真实Cloudflare调用身份、权限/Secret绑定、远程初始化、CPU/内存/长期运行；旧格式迁移和Phase5.1其他缺项仍未实施。

Phase5.1B须先单独授权账户只读核实、专用Mock资源、可信内部调用方、一次性Secret和明确目标/次数/截止。不得启用LOCAL_TESTING或自动进入远程实验。

无自动Git提交/推送，无部署。本阶段到此停止。

CLOUDFLARE_REMOTE_MUTATIONS: 0

REMOTE_DEPLOYMENTS: 0

REAL_YAHOO_REQUESTS: 0

LIVE_TRADING_ACTIONS: 0
