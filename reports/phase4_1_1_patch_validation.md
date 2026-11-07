# Phase 4.1.1 状态安全修补验收

全阶段离线；153/153测试通过，原有133项全部保留通过，新测试20项；无跳过。

状态安全修补范围验收PASS；**自动重建补跑仍BLOCKED，不能据此宣称完整无人值守恢复能力。**

## 缺陷与修补

- Existing revision ID kept CONFIRMED despite new higher-risk evidence → Only new REVISION_OBSERVATION evidence with explicit requires_review escalates to pending; evidence versions, risk audit and references commit together.
- Missing file implicitly became empty state → Strict load/save default. Explicit init only in a new existing isolated directory; prior backup/initialization/recovery artifacts block reset. Recovery is operator-selected and audited.
- Nonconsecutive sessions could still advance successful date → Per-symbol missing-session plan and CATCHUP_REQUIRED preserves checkpoint; other stocks can continue. Read-only RECONSTRUCTED_CATCHUP plan blocks automatic application.

同一修订ID保留全部证据，风险升级独立记入audit及review_history；pending不自动降低，REJECTED新证据安全阻断。已确认市场事件不撤销，只追加明确依赖风险；复核解除风险也留痕。
普通监控与辅助命令默认严格读取；--init-state是明确意图，需现存空白隔离目录。初始化收据及备份阻止通过删除主文件重建基线。缺失主文件列出经过完整校验的备份，不自动选取；恢复记录回滚风险。

## 场景回归

| 场景 | 结果 |
|---|---|
| U1 | PASS |
| U2 | PASS |
| U3 | PASS |
| U4 | PASS |
| U5 | PASS |
| M1 | PASS |
| M2 | PASS |
| M3 | PASS |
| M4 | PASS |
| M5 | PASS |
| C1 | PASS |
| C2 | PASS |
| C3 | PASS |
| C4 | PASS |
| C5 | PASS |

C2/C5使用固定、逐日、无未来价格的合成档案验证明确手工推进和中断恢复，不作为历史真实Point-in-Time行情认证。C3只产生RECONSTRUCTED_CATCHUP/PENDING_REVIEW只读计划，或拒绝与原始采集时间不符的回填输入，不改写旧状态。

## 完整回归

| 类别 | 总数 | 通过 | 失败 |
|---|---:|---:|---:|
| test_market_calendar | 8 | 8 | 0 |
| test_yahoo_nine_offline | 18 | 18 | 0 |
| test_phase3 | 42 | 42 | 0 |
| test_phase4 | 17 | 17 | 0 |
| test_phase4_1 | 24 | 24 | 0 |
| test_phase4_1_1 | 20 | 20 | 0 |
| test_phase4_1_guardrails | 6 | 6 | 0 |
| test_revision_diagnostics | 18 | 18 | 0 |

旧测试只将隐式创建夹具改为显式初始化；精确状态保护与数学断言保持。补丁前U1/M1/C1失败证据已保存。

## 九股隔离集成

1,139条历史修订、11条迁移歧义及共12条待复核完整保留；无虚假市场事件。九股全部指标、高点日期和WATCH档位逐项等于原Phase4，SPCX为PASS_PROVISIONAL。重复行情字节级幂等。

## 受保护状态

正式状态SHA256：`26e0f3f84e579b448e6e57fad9abd8b550568520c0088c0ff106f34eae727fa6`；160份既有证据/状态文件哈希完全不变。无正式迁移。

## 文件

- 修改：src/state.py
- 修改：src/monitor.py
- 修改：src/observations.py
- 修改：src/review.py
- 修改：src/phase4.py
- 修改：README.md
- 修改：tests/test_phase3.py
- 修改：tests/test_phase4_1.py
- 修改：tests/test_phase4_1_guardrails.py
- 新增：src/catchup.py
- 新增：tests/test_phase4_1_1.py
- 新增：diagnostics/validate_phase4_1_1.py

## 人工恢复路径

- `.venv/bin/python -m src.review --state ISOLATED/state.json --list-backups`
- `.venv/bin/python -m src.phase4 --state ISOLATED/state.json --recover-backup SELECTED_VERIFIED_BACKUP.json`
- `.venv/bin/python -m src.review --state ISOLATED/state.json --catchup-plan --input SAVED_PRICES.json`
- `.venv/bin/python -m src.monitor --state ISOLATED/state.json --input ORIGINAL_ARCHIVED_DAY.json --archived-catchup --archive-attestation "Verified original capture and source hashes" --output-dir ISOLATED/reports`

先保存检查点与账本；只选择通过验证的备份。补跑必须逐日提供有可信原始采集记录的完整档案，检查每日报告后再处理下一天；无法取得时保持阻断，不能改日期或删除状态绕过。

## 验收

- REVISION_RISK_ESCALATION: PASS
- PENDING_REVIEW_INTEGRITY: PASS
- MISSING_STATE_FAIL_CLOSED: PASS
- EXPLICIT_INITIALIZATION: PASS
- MISSED_SESSION_DETECTION: PASS
- EVENT_LEDGER_IDEMPOTENCY: PASS
- EXISTING_REGRESSION_TESTS: PASS
- INDICATORS_UNCHANGED: PASS
- FORMAL_STATE_UNCHANGED: PASS
- PROTECTED_EVIDENCE_UNCHANGED: PASS
- CATCHUP_SAFETY: BLOCKED
- PHASE_4_1_1_ACCEPTANCE: PASS
- CROSS_DAY_LIVE_VALIDATION: PENDING_LIVE_VALIDATION

## 未覆盖风险与限制

- No automatic backfill/reconstruction. Later adjusted histories do not establish historical Point-in-Time snapshots.
- Original archive capture timestamps and hashes are local evidence, not independently authenticated; operator must verify trust.
- Backup rollback may restore earlier event decisions; reconcile stable event IDs before future external delivery.
- Yahoo remains single source; SPCX dispute and live cross-day verification remain unresolved.
- No live requests, scheduled jobs, external delivery, trading, formal migration or Phase5 performed.
