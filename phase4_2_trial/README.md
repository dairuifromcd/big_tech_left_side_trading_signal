# Phase 4.2 有限期本地 DRY_RUN

仅运行 2026-11-03 至 2026-11-07 每日 09:00 Australia/Brisbane 的五次计划。
对应纽约完整交易日为 2026-11-02 至 2026-11-06；每次仍由市场日历动态校验。
失败也消耗认领次数；没有补足成功次数或自动补跑。

持久化状态固定为：
`/Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal/phase4_2_trial/state/monitor_state.json`

调度账本是 `execution_ledger.json`；市场事件账本位于状态的 `event_records`。
初始检查点为显式初始化的独立空 v2 状态，第一次有效行情建立 FIRST_BASELINE，
执行报告标记 TRIAL_FIRST_BASELINE。不迁移或修改正式 Phase 3 v1 状态。

## 调度与自动停止

- `config/launchd_manifest.json` 保存全部标签、安装路径、定义哈希。
- 五个采集 LaunchAgent 使用 LaunchOnlyOnce、无 KeepAlive、无 RunAtLoad。
- 每次结束后，短暂的独立清理进程验证服务已注销并删除自有安装 plist。
- 第五次结束或严重阻断后，清理所有剩余本次任务并写入 `acceptance/stop_receipt.json`。
- 2026-11-07 09:30 另有一个清理任务，无 Yahoo 请求权限逻辑、不算第六次采集。
  它用于处理终止、崩溃或没有完成第五次的情况；自身也被注销和清理。
- launchd 的日历没有年份字段，因此不能只依赖日历定义。实际注销、删除安装文件、
  程序日期和次数保护共同限制期限。项目 config 下的归档定义保留，不会自行调度。
- 启动迟到最多允许 15 分钟；不配置唤醒。睡眠或关机期间无法执行程序或注销，
  恢复后过期采集将被拒绝，清理才可执行，不能据此宣称准时执行成功。

## 第一轮前的条件

Mac 开机，UID 501 用户保持登录，在 Brisbane 09:00 保持唤醒且联网。
系统时区保持 Australia/Brisbane/AEST。无需保持 Codex App 打开。
保持项目、虚拟环境、锁定代码和试运行文件的位置与内容；改动将导致阻断。
已离线验证 CA 加载、真实 launchd 读写与双锁；Yahoo 网络可达性只在计划日期验证。
未修改系统安全设置、未安装软件、未使用管理员权限。

## 查看与停止

在项目目录中只读查看：

```sh
cat phase4_2_trial/acceptance/phase4_2_acceptance.md
cat phase4_2_trial/execution_ledger.json
/bin/launchctl print gui/501/com.rui.bigtech.phase42.run1-20261103
```

需提前停止时，可在普通 Mac Terminal 的项目目录执行以下命令。
它只移除本次清单所属任务，并保存停止收据，不会请求 Yahoo：

```sh
.venv/bin/python -m diagnostics.phase4_2_cleanup \
  /Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal/phase4_2_trial/config/launchd_manifest.json \
  all MANUAL_STOP
```

不要提前手动运行 `src.phase4_2 --run`；真实入口会拒绝日期越界并安全终止本次试运行。
不要删除状态、初始化收据、执行账本或 BLOCKED 标记来重新开始。
恢复需要核实归档、请求次数、状态备份和市场事件；当前不支持无人值守恢复。
可用以下只读命令列出经过验证的备份；不得自动选择或重建状态：

```sh
.venv/bin/python -m src.review --state phase4_2_trial/state/monitor_state.json --list-backups
```

## 验收范围

`preflight/regression_final.json` 记录离线回归；`preflight/cleanup_probe_receipt.json`
记录实际 launchd 自动清理证据。离线测试不消耗正式次数、不代表真实交易日执行。
每日证据保存在 collection、reports、logs，汇总位于 acceptance。
五个未来结果初始都为 PENDING。完整 PASS 只能由真实跨日采集及最终注销证据得出。
SPCX 始终保留 PASS_PROVISIONAL 与 YAHOO_ONLY/HISTORICAL_ANOMALY_UNVERIFIED。
没有真实触档时必须写 NOT_OBSERVED；不能把测试事件当作市场发现。

本阶段无交易、无正式状态迁移、不修改 ChatGPT Scheduled Task、不自动进入 Phase 5。
