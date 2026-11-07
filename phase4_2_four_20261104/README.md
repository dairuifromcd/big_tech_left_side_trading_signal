# 2026-11-04 至 11-07 四次有限期试运行

每天 Australia/Brisbane 10:00，共四次采集；目标美股完整交易日依次为
2026-11-03、04、05、06，并在运行时由纽约市场日历重新确认。

使用 2026-11-03 人工单次采集得到的 2026-11-02 九股 v2 状态作为基线。
原基线保留；新状态位于本目录 `state/monitor_state.json`，创建来源、原始
SHA256 和原提交版本记录于 config/trial.json 的 baseline。新试运行从自己的
commit_version=1 开始，不表示原状态回退或旧试运行恢复。

四次均串行采集同一九股，相邻请求起始至少5秒，跨批次另等30秒，每股一次，
不自动重试。失败消耗认领次数，HTTP429停止后续请求；异常、漏跑或不确定崩溃
将阻断后续运行。SPCX保持暂定验证和历史异常警告。无真实交易。

每次使用同一个新状态和执行账本；源码、配置、保护清单及历史证据均有哈希保护。
只排除 `.DS_Store`。不修改正式v1状态、原失败试运行或今日人工采集证据。

## 调度与总结

- 四个采集任务由 launchd 启动，不在安装时运行，不常驻重启。
- 各次结束后注销该任务并删除其安装plist。
- 第四次完成后生成 `acceptance/summary.json` 和 `acceptance/summary.md`，清理全部本次任务。
- 11月7日10:30另设一个仅汇总和清理的截止任务，用于处理中断；它不请求Yahoo，
  不是第五次采集，完成后也自行移除。
- `config/launchd_manifest.json` 保存五个任务的确切标签、安装路径及定义哈希。
- 开机登录后 launchd 才能运行；Mac必须联网并在计划时间保持唤醒。
  不配置系统自动唤醒。超过15分钟的迟到拒绝采集；睡眠/关机期间无法注销，
  恢复后程序拒绝过期采集并执行清理。无需保持Codex打开。
- 不新增ChatGPT自动任务，也不更改已有ChatGPT任务。

## 项目外影响与撤销

安装仅新增 `~/Library/LaunchAgents/com.rui.bigtech.phase42.four20261104.*.plist`
对应的四个采集任务和一个截止清理任务，并注册当前用户的launchd服务。
离线安装验收还会短暂注册两个本次前缀的测试服务，验证后自动清理。
不安装软件、不使用管理员权限、不修改系统设置或其他任务。

风险：后台采集依赖联网和唤醒，Yahoo可能拒绝访问或限流；可能因此提前终止。
代码或业务证据变化将安全阻断，不能保证取得四次成功。

若需停止，在项目目录的普通Terminal中执行：

```sh
.venv/bin/python -B -m diagnostics.phase4_2_four cleanup all MANUAL_STOP
```

该命令只处理本清单及前缀的任务，保留状态、账本、证据和停止收据。
更保守的替代方案是仅保留项目内配置、不安装LaunchAgents；这样不会自动执行。
不要手动提前执行 `run` 或删除BLOCKED、账本及状态来绕过保护。

## 只读查看

```sh
cat phase4_2_four_20261104/acceptance/summary.md
cat phase4_2_four_20261104/execution_ledger.json
/bin/launchctl print gui/501/com.rui.bigtech.phase42.four20261104.run1
```

未来四次初始都是PENDING。只以实际采集日志判定完成；完整跨日验收及最终移除
必须等真实运行后确认，自动补跑仍为NOT_VALIDATED。
