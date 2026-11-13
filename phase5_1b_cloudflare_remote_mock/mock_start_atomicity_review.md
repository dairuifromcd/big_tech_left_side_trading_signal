# Mock 启动事务原子性复核

MOCK_START_ATOMICITY: PASS_LOCAL_NODE_AND_WORKERD_SQLITE。

原问题：RemoteHarness 先独立更新 mock_experiment，再由 Coordinator 开启另一个事务创建 Run；后者失败会消耗预算而没有实际运行。修复后 RemoteHarness.start 持有唯一 Store.tx / SQLite transactionSync，包含窗口、预算、顺序、重叠状态检查，以及完整 H02 checkpoint、预算/执行声明写入、Run、12 READY Claims、checkpoint_control/run_checkpoints 和真实 updated 时间。任何同步异常均由现有事务回滚，不删除原状态、不重建基线。

Coordinator.start 保留对外事务包装；内部 startInTransaction 只提供给持有事务的可信同步调用者。Store.assertTransaction 拒绝无事务调用；transactionDepth 仅表示当前同步调用栈持有事务，finally 清理，不持久化，也不是第二套运行状态。内部方法不暴露 RPC、不接受外部时间/SQL/fault 参数。业务日期守卫仍是原 calendar/latestSession，Mock 仍仅内部映射两天固定 fixture。

beforeCreate 回调在完整 checkpoint 证明生成之后、Run 插入之前写 Mock 预算；不再重复执行第二次全量预检。H02 校验内容和已有执行声明检查均保留；certifyCheckpoint 的 generation 检查仍会拒绝预检期间发生的受保护数据变化。重复启动在既有窗口/ACTIVE 校验后返回 DUPLICATE，不再写预算；STOPPED 仍不可恢复，包括重复请求。

Node SQLite 与真正本地 workerd SQLite 共用19种场景，并在各自独立数据库执行：

| 场景 | 断言 |
|---|---|
| 完整 checkpoint 无效 | 拒绝、预算和完整数据库快照不变 |
| mock_experiment 写入后抛错 | 预算写入回滚，无持久 Run/Claim |
| Run 插入后抛错 | 预算与 Run 全部回滚 |
| 第6条 READY Claim 插入后抛错 | 前6条、Run及预算全部回滚 |
| checkpoint_control 更新后抛错 | checkpoint 标记及所有启动写入回滚 |
| run_checkpoints 写入后抛错 | Run checkpoint及所有启动写入回滚 |
| 最后 updated 更新后抛错 | 末尾失败也完整回滚 |
| 同一 Fixture 重复启动 | DUPLICATE、完整快照不变、runs仍1 |
| Fixture 顺序错误 | 拒绝、预算不消耗 |
| STOPPED | 拒绝、不可恢复 |
| Run / Collector / Alarm预算耗尽（3项） | 分别拒绝，不修改数据库 |
| 负数 / 超额预算（2项） | CORRUPT，fail closed |
| 原有 REQUEST_CLAIMED 声明无有效 Run | 完整 checkpoint 拒绝，不能跳过声明 |
| 重叠运行 | 拒绝，不消耗预算 |
| 窗口关闭 | 拒绝，不修改数据库 |
| 正常启动 | runs预算=1、execution=1、正式Run=1、READY Claims=12、checkpoint可用 |

每一失败/重复场景都比较操作前后**应用 schema、所有应用表（含 evidence/history/receipt/checkpoint/预算）的排序快照**，不是只检查行数。平台自身 `_cf_*` 内部表不在应用快照中。6个写入故障在语句实际执行之后抛错，避免“写入前就失败”掩盖回滚缺陷；回滚后移除测试注入再显式重试，均成功且只消耗一次预算。正常路径不调用 sync/Collector/外部网络；所有场景 source.calls=0，workerd outbound=0。Store 内存 SQL统计计数不属于数据库，失败操作后统计仍可增加，未声称统计计数也回滚。

新增19个Node场景+1个事务所有权测试+19个workerd子场景+1个父测试=40项；原241项完整保留，完整TS281/281。workerd故障 RPC 只在 `tests/mock-start-atomicity-worker.ts` 本地测试包中；remote bundle 的严格输入白名单证明不包含 tests 或故障入口。生产 remote-worker.ts 未改，无通用SQL/测试后门。

限制：这是本地 workerd/SQLite事务失败验证，并未声称验证真实云端进程终止、崩溃恢复、CPU、Duration 或平台Alarm计量。仍依赖Cloudflare存储 transactionSync 的平台语义。真实平台行为 PENDING_REMOTE_TEST。外部管理命令的 sync/arm 位于已提交事务之后；若其失败，已创建的Run和预算仍一致，按原幂等规则对账，不能当作整次网络调用可回滚。
