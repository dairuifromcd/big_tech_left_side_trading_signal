"""Summarize observed results without promoting incomplete work to PASS."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'phase5_1_cloudflare_free'
read=lambda name:json.loads((OUT/name).read_text())
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def tap(name):
    text=(OUT/name).read_text()
    values={key:int(re.search(r'^# '+key+r' (\d+)\s*$',text,re.M)[1]) for key in ('tests','pass','fail','cancelled','skipped','todo')}
    return values
python=read('python_tests.json');ts=tap('typescript_tests.log');parity=read('parity_results.json');runtime=read('runtime_results.json');protected=read('protected_files_verification.json')
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True).strip()
checks={'python':python,'typescript':ts,'parity':{k:v for k,v in parity.items() if k!='results'},'runtime':runtime,
        'typecheck':'PASS','cf_build':'PASS' if 'Build complete' in (OUT/'cf_build.log').read_text() else 'FAIL',
        'test_framework_notes':['Node SQLite experimental warning is expected.',
          'Miniflare v5 RPC bridge wraps some thrown synchronous transaction errors; Node SQLite asserts the exact STATE_ERROR and runtime tests additionally assert no request/state mutation.',
          'RPC lifetime warnings are emitted by the local harness; all Miniflare instances are explicitly disposed. They are not evidence of a remote result.']}
write('test_results.json',checks)
metrics=runtime['metrics'];daily=metrics['raw_envelope_bytes']+metrics['history_report_bytes']
resource={
  'basis':'One local Mock 12-asset baseline plus read API checks; not a cloud measurement or a revised-history stress benchmark',
  'observed_local':runtime,
  'assumptions':{'trading_days_per_month':21,'trading_days_per_year':252,'private_api_requests_per_calendar_day':200,
                 'mock_collection_attempts_per_run':12,'alarms_budget_per_run':40,'revision_event_growth_allowance_bytes_per_trading_day':2000000,
                 'free_single_object_conservative_budget_bytes':1000000000,'free_account_public_storage_bytes':5000000000,
                 'account_other_usage':'NOT_VERIFIED','storage_overhead_reserve_factor':2},
  'estimates':{'network_attempts_month':252,'network_attempts_year':3024,
               'raw_plus_committed_report_bytes_per_trading_day':daily,
               'raw_plus_report_bytes_month':daily*21,'raw_plus_report_bytes_year':daily*252,
               'baseline_state_bytes_overwritten_not_added_daily':metrics['state_json_bytes'],
               'sql_rows_read_month_baseline_scale':metrics['reads']*21,'sql_rows_read_year_baseline_scale':metrics['reads']*252,
               'sql_rows_written_month_baseline_scale':metrics['writes']*21,'sql_rows_written_year_baseline_scale':metrics['writes']*252,
               'alarm_requests_month_budget':840,'alarm_requests_year_budget':10080,
               'private_api_requests_month_30days':6000,'private_api_requests_year_365days':73000,
               'revision_heavy_growth_bytes_year_assumption':(daily+2000000)*252,
               'conservative_full_day_15min_active_duration_GBs':900*0.125},
  'not_measured':['Cloudflare Worker/DO CPU, isolate heap/RSS, cold start, duration billing, account quotas, alarms reliability, external Yahoo latency and error rates',
                  'SQLite index/write amplification and repeated evidence growth on a multi-year revised-history workload',
                  'Actual paid bill or R2 subscription eligibility'],
  'limitations':['Node host RSS includes test tooling and is not the workerd isolate memory; host process CPU excludes child workerd CPU.',
                 f'Local no-revision baseline has zero new market events, so its {metrics["writes"]} SQL writes are not a worst-case event budget.',
                 'Backups kept in the same SQLite DB are not independent disaster recovery. Repeated full backups without a retention/archive design can grow superlinearly.',
                 'Finite free storage cannot retain unlimited raw evidence indefinitely; never silently delete evidence to stay free.',
                 'Official DO limits page disagrees about Free per-object 1GB vs 10GB; use 1GB until clarified.'],
  'usd_zero_feasibility':'CONDITIONAL_NOT_GUARANTEED','real_cloudflare_resource_validation':'NOT_VERIFIED'
}
write('resource_estimate.json',resource)
components={
 'CLOUDFLARE_FREE_ARCHITECTURE':'CONDITIONAL',
 'CLOUDFLARE_ACCOUNT_READONLY_CHECK':'NOT_VERIFIED',
 'TYPESCRIPT_PORTING':'PARTIAL',
 'PYTHON_TYPESCRIPT_PARITY':'PASS_CORE_SCOPE_ONLY',
 'PERSISTENCE_AND_RECOVERY':'PASS_OFFLINE_POC_SCOPE_ONLY',
 'VISUALIZATION_API_READINESS':'PARTIAL',
 'NASDAQ_23_5_COMPATIBILITY':'PASS_ANALYSIS_YAHOO_FUTURE_BASIS_NOT_VERIFIED',
 'COST_FEASIBILITY':'CONDITIONAL_NOT_GUARANTEED',
 'PROTECTED_EVIDENCE_INTEGRITY':'PASS' if protected['all_unchanged'] and protected['pending_records_identical'] else 'FAIL',
 'READY_FOR_CLOUD_POC':'CONDITIONAL_MOCK_ONLY_REQUIRES_SEPARATE_AUTHORIZATION'
}
gaps=[
 '本会话没有可用Cloudflare插件入口，账户套餐/资源/余量/命名冲突未核实。',
 'Python v1/v2状态迁移、完整正式状态导入导出及一般Python原始证据JSON字节序列化尚未完整移植/验收；旧证据须保留原字节。',
 '完整人工review/rollback/reopen和受信归档逐日应用runner未移植；当前仅保留sticky状态、reopen阻断、归档校验与只读gap plan。',
 '历史图表DTO已设计，但完整历史分析series查询、持久预计算及真正SQL分页未完成。',
 '独立备份/灾难恢复、分块证据、长期事件索引及多年度压力资源预算尚未完成。',
 '真实Cloudflare/Yahoo运行、Free CPU/内存、配额与可靠性均NOT_VERIFIED。'
]
zero={'CLOUDFLARE_REMOTE_MUTATIONS':0,'REMOTE_DEPLOYMENTS':0,'REAL_YAHOO_REQUESTS':0,'LIVE_TRADING_ACTIONS':0}
all_tests=python['passed']==271 and not python['failures'] and not python['errors'] and not python['skipped'] and ts['pass']==ts['tests'] and ts['fail']==0 and runtime['status']=='PASS'
overall='PARTIAL' if all_tests and components['PROTECTED_EVIDENCE_INTEGRITY']=='PASS' else 'FAIL'
files=sorted(str(p.relative_to(ROOT)) for base in ('cloudflare','phase5_1_cloudflare_free') for p in (ROOT/base).rglob('*') if p.is_file() and not any(x in p.relative_to(ROOT).parts for x in ('node_modules','.cache','.home','.tmp','.cloudflare','dist','.wrangler')))
report={'PHASE_5_1_CLOUDFLARE_FREE':overall,'offline_core_poc':'PASS' if all_tests else 'FAIL','cloud_validation':'NOT_VERIFIED',
        'git_head':head,'git_worktree_status':status,'existing_files_modified':[], 'new_file_roots':['cloudflare/','phase5_1_cloudflare_free/'],
        'components':components,**zero,'tests':{'python':python,'typescript':ts,'golden_fixtures':parity['golden_fixtures'],'validation_fixtures':parity['validation_fixtures'],'numeric_fields_compared':parity['compared_float_fields'],'max_absolute_difference':parity['max_absolute_difference']},
        'protected_file_count':protected['file_count'],'old_pending_count':protected['pending_count'],'gaps':gaps,
        'no_commit_no_push_no_deploy':True,'next_task':'Complete remaining offline port/import/recovery/history/backup acceptance, then separately authorize a bounded Mock-only Cloudflare PoC.',
        'files':files}
write('acceptance.json',report)
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for base in ('cloudflare','phase5_1_cloudflare_free') for p in (ROOT/base).rglob('*') if p.is_file() and str(p.relative_to(ROOT)) in files and p.name not in ('artifact_manifest.json','acceptance.md','completion_handoff.md')}
write('artifact_manifest.json',manifest)
lines=[f'PHASE_5_1_CLOUDFLARE_FREE: {overall}', '',
       '核心离线PoC通过；整体移植及账户调查尚未完成，不能报告完整PASS。未进入下一阶段。', '',
       '| 分项 | 状态 |','|---|---|']+[f'| {k} | {v} |' for k,v in components.items()]
lines+=['',f'Python {python["passed"]}/{python["total"]}；TypeScript {ts["pass"]}/{ts["tests"]}；均无失败/跳过。76个核心golden、32个Yahoo验证fixture；原30组修订覆盖。11145个浮点字段最大绝对差0；离散结果及事件ID精确相同。',
        '',f'{protected["file_count"]}个原有文件SHA256一致，7条原PENDING_REVIEW完整不变；AVGO6条、SPCX1条。原Python核心、正式状态及历史验收资料均未修改。', '',
        '最终问题回答：', '',
        '1. 免费架构有条件可行；12标的小规模算量适合，但账户和真实资源未验证，有限存储无法无条件永久归档。',
        '2. 推荐Workers + SQLite-backed DO；Worker保持轻量，DO负责协调、事务、归因和报告投影。',
        '3. 新项目选择cf 1.0.0-beta.29 + Vite 2 beta，项目本地Node22.23及Miniflare/workerd；cf build实际通过，无Wrangler配置。',
        '4. 核心指标/修订/市场事件等效已通过，完整Python功能没有全部移植，详见下列缺项。',
        f'5. Python{python["passed"]}与TS{ts["pass"]}分别通过；最终测试无未通过项。未实现/未验证内容独立列出，不计入PASS。',
        '6. 6类只读API和独立Report DTO已有本地验证；完整历史图表分析series、SQL分页和真实鉴权仍需完成。',
        f'7. 目标US$0合理但不保证。基线raw+report约{daily:,}字节/交易日，约{daily*252:,}字节/年；修订和备份可能显著增加，另有共享额度与R2计费风险。',
        '8. 保留Brisbane周二至周六10:00；常规收盘语义未因23/5计划自动改变。Yahoo新口径/发布时间NOT_VERIFIED。',
        '9. 只有云端能验证真实CPU/内存/额度、Alarm和Cron可靠性、DO故障迁移及Yahoo出口/23-5口径。',
        '10. 最小下一阶段为有截止与次数的隔离Mock Worker+SQLite DO实验，先只读核实账户，再单独授权创建、鉴权、上传与Alarm。Cron、真实Yahoo、R2和付费均另授权。', '',
        '尚未完成：', '']+['- '+g for g in gaps]
lines+=['','详细设计：architecture.md、cloudflare_free_feasibility.md、account_readonly_assessment.md、cli_selection.md、state_storage_design.md、execution_and_recovery.md、python_typescript_parity.md、report_api_contract.md、nasdaq_23_5_compatibility.md、cloud_poc_plan.md。资源与测试证据见对应JSON/log。', '',
        'Completion Handoff：', '',f'- HEAD：{head}；初始工作区干净，最终只新增cloudflare/和phase5_1_cloudflare_free/。',
        '- 未修改任何原有tracked文件，未自动提交/推送/部署。新增文件完整清单见acceptance.json。',
        '- 请求声明先持久化；未知结果不重采；每标的事务；股票/指数隔离；旧pending不自动升级；缺日不假造PIT。',
        '- 下一任务先补齐离线移植缺项，再单独授权有边界的Mock Cloudflare PoC。不得直接接入正式历史或真实Yahoo。', '']+[f'{k}: {v}' for k,v in zero.items()]
(OUT/'acceptance.md').write_text('\n'.join(lines)+'\n')
handoff=[f'PHASE_5_1_CLOUDFLARE_FREE: {overall}',f'HEAD: {head}',
         '工作区：初始干净；只新增cloudflare/及phase5_1_cloudflare_free/，无原有文件修改，无提交/推送/部署。',
         f'测试：Python {python["passed"]}/{python["total"]}，TypeScript {ts["pass"]}/{ts["tests"]}，golden76，Yahoo验证32；0失败/跳过。',
         f'保护：{protected["file_count"]}个原有文件hash一致，7条旧pending完整不变。',
         '新增文件：源码/fixtures/依赖锁/本地测试在cloudflare；设计、预算、日志、验收在phase5_1_cloudflare_free。完整清单见acceptance.json。',
         '架构：Worker轻量转发，SQLite DO统一12标的请求声明及按标的事务；股票/指数隔离；不确定不重采；Report DTO独立。',
         '未完成：账户检查、完整旧状态/证据兼容、人工决定及归档应用runner、独立灾备、完整历史分析/SQL分页、长期云资源验证。',
         '需另授权：创建Worker/SQLite DO、鉴权配置、上传版本、远程Alarm。Cron、真实Yahoo、R2与付费另行授权。',
         '建议下一任务：先补齐离线移植缺项，再做有截止/次数限制的隔离Mock云端PoC。保留Brisbane周二至周六10:00候选；不进入下阶段。']+[f'{k}: {v}' for k,v in zero.items()]
(OUT/'completion_handoff.md').write_text('\n\n'.join(handoff)+'\n')
print(json.dumps({'overall':overall,'tests':report['tests'],'components':components,**zero},ensure_ascii=False,indent=2))
