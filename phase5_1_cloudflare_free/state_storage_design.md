# 状态、事件及持久化

SQLite schema v1独立于Python文件schema v2；算法rules_version和事件模型版本维持原值。

| 表 | 用途 / 事务约束 |
|---|---|
| meta | 显式初始化receipt、schema、恢复receipt |
| runs | 每目标交易日唯一运行声明 |
| claims | date/symbol唯一请求声明、ordinal、状态、开始/完成、错误和raw hash |
| evidence | 请求原始响应封装、原字节字符串、SHA256及来源；不可覆盖 |
| states | category/symbol主键，单调版本、canonical JSON、版本与body共同哈希 |
| events | category/event_id主键，完整证据版本、sticky状态及audit trail |
| history | 仅成功提交的Report DTO历史，版本及内容哈希 |
| backups | 显式选择的本地checkpoint封装，完整hash |

category取stocks或indices。单标的状态、事件、报告历史和COMMITTED声明在一个transactionSync中提交。单标的异常回滚全部暂存变更；其他已成功标的不回滚。计算/网络不在事务内，提交时比较priorVersion以拒绝陈旧候选。

请求声明先写SQLite，再由DO adapter等待storage.sync，之后才允许Mock collector执行。实际实现从响应完成时间再等待5秒，分批边界再加30秒；这样持久化确认很慢也不会缩短真实请求起始间隔。未知网络结果不重试。

原事件ID仍使用Python sort_keys、默认separator、ensure_ascii对应的语义JSON SHA256。它只含字符串、整数阈值与null；stock/index字段及模型不同。标准化float64价格map另实现Python浮点序列化，golden逐例对照hash。

一般Python JSON里的int/float类型在JSON.parse后可能无法恢复，因此新证据采用明确的js-canonical-v1哈希方案。旧证据ID/hash不重写、不冒充已经字节等效：应永久保留原文件字节及source hash，以独立封装引用。7条旧pending仅测试隔离导入，正式导入工具与逐证据兼容验收尚未实现。

不自动初始化：正常请求缺receipt、状态损坏、已COMMITTED后丢失state或schema不兼容均停止。只读API启动不会DDL/写表；显式testInit才建立空schema与receipt。既有初始化不能再次执行以重置历史。

备份验证覆盖同checkpoint下丢失状态的显式修复；请求声明、事件、证据、运行和历史必须与备份一致，否则BACKUP_RECONCILIATION_REQUIRED。不能回滚请求声明或旧人工决定。当前本地备份仍在同SQLite故障域，不是独立灾备；跨数据库/对象或R2的受控恢复、签名manifest、claims并集/冲突核对需后续实施。

升级流程：只读检查schema/rules/model → 导出不可变manifest及独立备份 → 在复制品执行显式迁移 → 全量验证ID/阈值/pending → 人工授权切换。未知版本当前直接拒绝；没有实现Python v1→v2迁移器或生产自动schema升级。不能改变rules_version后假称旧ID仍适用。

长期设计需将重复previous checkpoints内容寻址存储、为事件建立symbol/date索引、按capture保留完整原始证据并分块；当前PoC只提供小数据安全基础，API分页为内存分页，不能据此宣称无界历史可扩展。
