# Phase5.1B人工审阅前置条件

本阶段只具备提交人工审阅的本地安全基础，不授权或启动远程实验。

- 先核对Cloudflare插件、账户套餐、DO SQLite能力、配额余量及资源名冲突；不要把网页额度视为账户实测。
- 单独批准专用Mock Worker、SQLite DO namespace/实例、一次性初始化Secrets和可信内部调用方所需权限。不得导入正式历史、连接真实Yahoo或开启LOCAL_TESTING。
- 精确指定将初始化的DO ID、operation、request_id、operator、authorization_reference、原因、执行次数与实验截止时间。新的初始化token只存Secret，不进Git或日志。
- 实际管理入口及调用身份须另审查。现有代码只准备了内部受控RPC；没有公开管理HTTP入口，也没有远程初始化执行器。Cloudflare身份和binding权限验证状态仍为NOT_VERIFIED。
- 执行前保留该实例应为空的只读证明；已有任何状态、事件、claims、证据、旧表或Alarm均停止，不删除数据来“修复”初始化资格。
- 初始化后核对receipt/hash/schema/审计、关闭初始化policy/回收一次性权限的步骤也需纳入授权。初始化只执行一次，不循环重试。
- 后续只做有截止/次数限制的Mock调用及真实资源指标检查。Cron、真实Yahoo、R2、付费和部署扩围各自需要额外授权。
- 旧receipt/旧Python事件若出现migration required，保留所有原数据并停止；不在Phase5.1B中顺带迁移或确认旧pending。

预计低频Mock可能落在Free余量内，但账户及真实消耗未知，不能保证US$0。所有远程创建、部署、Secrets、Alarm与清理均为REQUIRES_SEPARATE_AUTHORIZATION。当前远程修改/部署/真实Yahoo/交易操作全部为0。
