# H02 完整Checkpoint预检

`Store.validateFullCheckpoint()` 是同步、只读校验，不修复任何记录。每日启动在同一个 transactionSync 中依次执行：

1. 核对初始化receipt/audit、schema及安全控制结构。
2. 读取所有已提交states，检查category/symbol、正整数版本、版本+内容hash、事件模型、rules、日期/身份/Close/Adj Close、指标及threshold state。
3. 读取所有event rows，先检查内容hash，再检查数据库key、event_id及原语义ID、category/symbol/model、事件类型/阈值/状态。
4. 验证非空Evidence Versions、明确hash scheme、每版hash、去重；验证audit链、初始/后续合法动作、最终状态和依赖标记。
5. 按symbol验证confirmed事件与confirmed阈值精确对应、三个确认别名一致，pending引用及未解决revision引用精确对应；验证依赖事件、日期与symbol。
6. 验证原始证据hash、request/claim引用、已提交状态存在、当前状态对应的原始验证序列及最新历史Report DTO。
7. 计算验证结果，随后才创建运行与12个任务声明、存储验证标记。任意失败整笔回滚，无Collector调用，不新建baseline。

每条native事件必须使用 `js-canonical-v1` 的明确证据格式。旧Python证据没有该scheme时不重新计算替代hash，不修改status/ID，返回 `LEGACY_EVIDENCE_MIGRATION_REQUIRED`。未知audit迁移格式同样阻断，而不是推测已合法复核。7条原pending隔离副本的测试验证了“完整不变且不能绕过启动预检”。

日内保护不靠未验证的内存缓存。SQLite触发器维护generation；程序核对触发器集合和SQL定义，删除/替换/增加触发器都会阻断。每次tick、请求声明事务及DO等待storage.sync之后、实际Mock Collector之前，都检查已验证generation和本次运行绑定。运行开始后事件被改写也不能继续采集。

原始响应持久化与单标的提交是受控写入：事务开始前验证标记仍有效，校验实际相关记录，原子提交，再推进generation标记。单标的提交校验相关事件而不重做全池预检；保留旧Evidence Versions/audit前缀、pending/rejected决定及依赖引用。未经授权的旧决定改变被拒绝，成功的其他symbol不被污染。

完整预检每新交易日一次；API不调用该全量验证。测试确认12标的运行及多次API读取后 fullValidations 仍为1。若初始化元数据/状态/账本在验证后改变，当前运行阻断并要求人工调查；不自动重新证明或清除不确定声明。

边界：SQL mutation generation适用于通过受控SQLite接口发生的变化；不是对拥有数据库/部署权限的攻击者提供独立密码学认证，也不是磁盘位翻转的连续检测。每日完整hash校验、SQLite原子性及平台存储可靠性共同构成前提。真实CPU/内存、平台故障与认证边界仍须未来云端验证。

未扩大到完整Python状态迁移、人工Review/Rollback/Reopen、独立灾备或历史分页。unsupported格式保守阻断。Phase5.1的总体PARTIAL结论仍然成立。
