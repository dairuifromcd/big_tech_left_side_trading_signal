# Adj Close 修订与事件归因改进验收

ADJCLOSE_REVISION_REFINEMENT: PASS

全程离线：271/271测试通过，原237项完整保留，新增34项，无跳过；真实网络请求0。

当前指标始终使用最新验证通过的Adj Close；旧/新基础均重算前日及当日，混合基础结果仅供诊断。修订与市场观察分别留痕。
股票保留Close、身份和调整单位安全检查；指数不以Close单独变化阻断Adj Close事件。
完整价格修订证据若可证明在前日/当日事件窗口之外，可不阻断新独立事件；旧待复核状态不变。未知证据和相关修订继续安全待复核。
股票按阈值保留可证明的新跨越和有争议候选；指数保留更保守的极值修订检查，避免把仅有当前档位的共同性误当新跨档。

## 修改理由

src/monitor.py只增加事件上下文传入及报告展示，以便基于完整旧修订证据判定依赖。未改state.py、signals.py、indicators.py、catchup.py或采集身份规则。

## 场景对照

| 场景 | 类别 | 修改前市场候选 | 修改后市场候选 | 最新指标正确 |
|---|---|---|---|---|
| unchanged | stock | 20:CONFIRMED | 20:CONFIRMED | True |
| micro | stock | 20:CONFIRMED | 20:CONFIRMED | True |
| material | stock | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| high_same_tier | stock | 无 | 无 | True |
| revision_only | stock | 20:PENDING_REVIEW | 无 | True |
| mixed_material | stock | 20:PENDING_REVIEW, 30:PENDING_REVIEW | 20:PENDING_REVIEW, 30:PENDING_REVIEW | True |
| disagreement | stock | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| one_basis_only | stock | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| unrelated_material | stock | 20:PENDING_REVIEW | 20:CONFIRMED | True |
| near_boundary | stock | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| close_only | stock | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| prior_unrelated | stock | 20:PENDING_REVIEW | 20:CONFIRMED | True |
| prior_related | stock | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| prior_unknown | stock | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| prior_source_risk | stock | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| unchanged | index | 20:CONFIRMED | 20:CONFIRMED | True |
| micro | index | 20:PENDING_REVIEW | 20:CONFIRMED | True |
| material | index | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| high_same_tier | index | 无 | 无 | True |
| revision_only | index | 无 | 无 | True |
| mixed_material | index | 无 | 20:PENDING_REVIEW, 30:PENDING_REVIEW | True |
| disagreement | index | 无 | 20:PENDING_REVIEW | True |
| one_basis_only | index | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| unrelated_material | index | 20:PENDING_REVIEW | 20:CONFIRMED | True |
| near_boundary | index | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| close_only | index | 20:CONFIRMED | 20:CONFIRMED | True |
| prior_unrelated | index | 20:PENDING_REVIEW | 20:CONFIRMED | True |
| prior_related | index | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| prior_unknown | index | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |
| prior_source_risk | index | 20:PENDING_REVIEW | 20:PENDING_REVIEW | True |

## AVGO 2026-11-06

原始类型DEEPER_DRAWDOWN及PENDING_REVIEW保留；候选不是当天新增已确认下跌。
daily_new_deepening=False；同一最新基础daily_drawdown_change_pp=0.450062；累计锚点加深=5.946643pp；candidate_confirmed=False。
与存档前日指标直接相减的展示差值另存为0.450058pp，避免把不同基础当作市场证明。原始事件ID保持一致。

## 原系统保护

412个非授权改动文件SHA256全部不变；7条原始PENDING_REVIEW完整一致。股票9股和指数3标的的归档回放均在新隔离目录完成，检查点字节幂等。

待复核数量并非越少越好：保留以前被丢弃的候选会增加待复核；本次只减少可严格证明无关的全局阻断，不确认、拒绝或删除旧记录。

## Phase5

Suitable for Phase5 design discussions; not production authorization. Unattended recovery, long-term reliability and explicit review workflow remain unvalidated.

## 限制

- Index extrema revisions remain conservatively pending even if a coarse event type agrees.
- Unknown legacy evidence or source/unit risk cannot be automatically discharged.
- Deepening anchor dependencies remain conservative; daily semantics are improved without rewriting historical candidates.
- No new Yahoo requests, scheduler or external services used. No old pending status modified.
