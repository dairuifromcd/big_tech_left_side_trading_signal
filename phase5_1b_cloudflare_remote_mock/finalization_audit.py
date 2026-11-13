"""Project-local finalization evidence. No auth discovery or cloud calls."""
from pathlib import Path
import collections
import hashlib
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(__file__).resolve().parent

def read(name): return json.loads((OUT/name).read_text())
def write(name,value): (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True)

base=read('finalization_baseline.json')
allow={'cloudflare/src/coordinator.ts','cloudflare/src/remote-harness.ts','cloudflare/src/storage.ts',
       'cloudflare/cloudflare.config.ts','cloudflare/scripts/local.mjs','cloudflare/tests/remote-mock.test.ts',
       'cloudflare/tests/remote-mock-runtime.test.ts','cloudflare/scripts/remote_mock_build_audit.py'}
protected={n:h for n,h in base['sha256'].items() if n not in allow and not n.startswith('phase5_1b_cloudflare_remote_mock/')}
unexpected=[n for n,h in protected.items() if not (ROOT/n).is_file() or sha(ROOT/n)!=h]
allnames=git('ls-files','--others','--exclude-standard').splitlines()
allowed_new={'cloudflare/tests/mock-start-atomicity-fixture.ts','cloudflare/tests/mock-start-atomicity-worker.ts'}
new_outside=[n for n in allnames if n not in allowed_new and not n.startswith('phase5_1b_cloudflare_remote_mock/')]
original=read('baseline.json')
state=json.loads((ROOT/'phase4_2_four_20261104/state/monitor_state.json').read_text())
pending={k:v for k,v in state['event_records'].items() if v['status']=='PENDING_REVIEW'}
pending_hash=hashlib.sha256(json.dumps(pending,sort_keys=True,separators=(',',':')).encode()).hexdigest()
historical=lambda prefix:all((ROOT/n).is_file() and sha(ROOT/n)==h for n,h in base['sha256'].items() if n.startswith(prefix))
protected_result={'baseline':'finalization_baseline.json at current HEAD, never overwritten','head':git('rev-parse','HEAD').strip(),
    'all_protected_unchanged':not unexpected and not new_outside,'protected_file_count':len(protected),
    'unexpected_changes':unexpected,'unexpected_new_files':new_outside,
    'intentional_modified_code_files':sorted(n for n in allow if sha(ROOT/n)!=base['sha256'][n]),
    'phase51_acceptance_unchanged':historical('phase5_1_cloudflare_free/'),
    'phase51a_acceptance_unchanged':historical('phase5_1a_hardening/'),
    'phase42_history_unchanged':all(historical(p) for p in ['phase4_2_four_20261104/','phase4_2_manual_20261103/','phase4_2_trial/']),
    'pending_count':len(pending),'pending_records_identical':len(pending)==original['pending_count'] and pending_hash==original['pending_sha256'],
    'initial_user_file_contents_preserved':{n:content in (ROOT/n).read_text() for n,content in base['initial_user_files'].items()}}
write('protected_files_verification.json',protected_result)
log=(OUT/'typescript_tests.log').read_text()
counts={n:int(re.search(r'^# '+n+r' (\d+)\s*$',log,re.M)[1]) for n in ['tests','pass','fail','cancelled','skipped','todo']}
oldlog=git('show','HEAD:phase5_1b_cloudflare_remote_mock/typescript_tests.log')
subtests=lambda s:collections.Counter(re.findall(r'^\s*# Subtest: (.*)$',s,re.M))
missing=list((subtests(oldlog)-subtests(log)).elements())
counts.update(baseline_total=241,baseline_tests_retained=not missing,missing_baseline_test_names=missing,added=counts['tests']-241)
write('typescript_tests.json',counts)
python=read('python_tests.json');parity=read('parity_results.json');atomic=read('mock_start_atomicity_workerd_results.json')
remote=read('remote_mock_local_results.json');runtime=read('remote_mock_workerd_results.json');hardening=read('hardening_runtime_results.json')
build=read('remote_build_audit.json');default=read('default_build_audit.json');prep=read('preparation_build_audit.json')
m=read('deployment_manifest.json')
for key in ['MOCK_START_UTC','MOCK_END_UTC','MOCK_INIT_END_UTC']:
    assert m['bindings'][key]==build['worker_config']['env'][key]['value']
assert build['worker_config']['env']['REMOTE_MOCK_ENABLED']['value']=='DISABLED_PENDING_GATE_B'
assert m['resources']['worker']['candidate_name']==build['resources']['worker']
assert m['resources']['durable_object']['class']==build['resources']['class']
assert m['experiment']['fixture_dates']==remote['fixtures']
assert not m['gate_b_approved'] and not m['authorization']['gate_b_approved'] and not m['can_execute_gate_b']
assert prep['mode']=='p51b-identity-prep' and not prep['enabled']
assert prep['bundle_sha256']==build['bundle_sha256'] and prep['reviewed_code_sha256']==build['reviewed_code_sha256']
assert prep['worker_config']['env']['MOCK_START_UTC']['value']=='2026-11-15T22:00:00Z'
for key,value in m['experiment']['initialization_timing']['stage1_uninitialized_preparation_bindings'].items():
    if value=='ABSENT': assert key not in prep['worker_config']['env']
    else: assert prep['worker_config']['env'][key]['value']==value
assert 'mock-start-atomicity' not in '\n'.join(build['esbuild_inputs']+build['vite_sources'])
m['code_version'].update(reviewed_code_sha256=build['reviewed_code_sha256'],bundle_sha256=build['bundle_sha256'],bundle_bytes=build['bundle_bytes'],worker_config_sha256=build['worker_config_sha256'])
m['code_version']['preparation_worker_config_sha256']=prep['worker_config_sha256']
m['code_version']['preparation_bundle_sha256']=prep['bundle_sha256']
m['cost']['local_sqlite_page_bytes']=remote['local_sqlite_page_bytes']
write('deployment_manifest.json',m)
passed=(python['passed']==python['total']==271 and not python['network_attempts'] and
    counts['tests']==counts['pass']==281 and not any(counts[k] for k in ['fail','cancelled','skipped','todo']) and not missing and
    parity['passed']==parity['golden_fixtures']==76 and parity['validation_fixtures']==32 and parity['compared_float_fields']==11145 and parity['max_absolute_difference']==0 and
    atomic['status']=='PASS' and len(atomic['cases'])==19 and atomic['outbound_requests']==atomic['collector_calls']==0 and
    all(c['snapshot_identical'] for c in atomic['cases'] if c['scenario']!='success') and
    all(c['retry']=='STARTED' for c in atomic['cases'] if c['fault_reached']) and
    remote['runs']==2 and remote['collector_calls']==24 and remote['alarm_ticks']==26 and
    runtime['outbound_requests']==0 and runtime['kill_alarm_cancelled'] and runtime['persisted_stop'] and
    hardening['blocked_checkpoint_cases']==15 and hardening['collector_calls_for_blocked_cases']==hardening['outbound_requests']==0 and
    read('runtime_results.json')['status']=='PASS' and
    build['status']==default['status']==prep['status']=='PASS_LOCAL_ONLY' and not build['enabled'] and
    'Build complete' in (OUT/'cf_default_build.log').read_text() and
    'dry-run' in (OUT/'cf_remote_dry_run.log').read_text().lower() and not (OUT/'typecheck.log').read_text().strip() and
    protected_result['all_protected_unchanged'] and protected_result['pending_records_identical'] and
    all(protected_result['initial_user_file_contents_preserved'].values()))
components={
    'DASHBOARD_ACCOUNT_EVIDENCE':'USER_REPORTED_DASHBOARD',
    'WORKERS_FREE_PLAN':'USER_REPORTED_DASHBOARD (Free / US$0); not CLI/API verified',
    'DURABLE_OBJECTS_ACCOUNT_BASELINE':'USER_REPORTED_DASHBOARD (namespace0 / reported usage0)',
    'MOCK_START_ATOMICITY':'PASS_LOCAL_NODE_AND_WORKERD_SQLITE',
    'REMOTE_MOCK_HARNESS':'PASS_LOCAL_ONLY', 'KILL_SWITCH':'PASS_LOCAL_ONLY',
    'PYTHON_REGRESSION':'PASS 271/271','TYPESCRIPT_REGRESSION':'PASS 281/281 (241 retained +40)',
    'GOLDEN_PARITY':'PASS 76 +32 Yahoo /11145 numeric fields /max diff0',
    'PROTECTED_FILES_INTEGRITY':'PASS' if protected_result['all_protected_unchanged'] else 'FAIL',
    'DEPLOYMENT_MANIFEST':'PASS_LOCAL_DISABLED_CANDIDATE_ONLY',
    'GATE_B_AUTHENTICATION_DESIGN':'READY_FOR_AUTHORIZATION_REVIEW; actual grants/cf compatibility NOT_VERIFIED',
    'READY_FOR_GATE_B_AUTHORIZATION_REVIEW':bool(passed)}
zero={n:0 for n in ['CLOUDFLARE_REMOTE_MUTATIONS','REMOTE_DEPLOYMENTS','REAL_YAHOO_REQUESTS','LIVE_TRADING_ACTIONS','PRODUCTION_STATE_MUTATIONS']}
results={'PHASE_5_1B_GATE_A_FINALIZATION':'PASS' if passed else 'FAIL','components':components,'python':python,
    'python_initial_attempt':{'passed':267,'total':271,'errors':4,'network_attempts':[],'cause':'macOS noncanonical system TMPDIR symlink; no code changes','retained_log':'python_initial_environment_failure.log'},
    'python_final_process_environment':{'TMPDIR':str(ROOT/'cloudflare/.tmp'),'PYTHONDONTWRITEBYTECODE':'1'},
    'typescript':counts,'golden':{k:v for k,v in parity.items() if k!='results'},
    'atomic_workerd':atomic,'remote_mock':remote,'remote_runtime':runtime,'h01_h02_runtime':hardening,
    'typecheck':'PASS','cf_local_build':'PASS','remote_mode_dry_run':'PASS_CREDENTIAL_FREE_NO_PROVISION','preparation_mode_dry_run':'PASS_CREDENTIAL_FREE_NO_PROVISION',
    'build_audit':{'source_sha256':build['reviewed_code_sha256'],'bundle_sha256':build['bundle_sha256'],'bundle_bytes':build['bundle_bytes']},
    'protected_files':protected_result,'real_cloud_api_account_evidence':'NOT_VERIFIED_NO_API_CALLS',
    'cloud_metrics':'PENDING_REMOTE_TEST',**zero,'GATE_B_APPROVED':False}
write('test_results.json',results)
summary='''# Gate A Finalization — 当前验收（2026-11-13）

PHASE_5_1B_GATE_A_FINALIZATION: **%s**

READY_FOR_GATE_B_AUTHORIZATION_REVIEW: **%s**；GATE_B_APPROVED: **false**。仅本地准备完成，不代表已认证、部署或可直接进入 Gate B。以下表格为当前结论；后续历史正文按原样保留，其旧窗口/待核验状态已被本节和新授权清单替代。

| 分项 | 当前结果 |
|---|---|
'''%('PASS' if passed else 'FAIL','true' if passed else 'false')
summary+='\n'.join('| '+k+' | '+str(v)+' |' for k,v in components.items())
summary+='''

启动事务、Node/workerd19场景和重试证据见 mock_start_atomicity_review.md。Python271/271、TS281/281（原241无删除/跳过），两轮合成24 Collector/26 ticks，15类H02请求前阻断，Golden76、Yahoo32、11145字段最大差异0。本轮Python首试的4个TMPDIR路径错误日志保留，改用进程级项目临时目录后全通过，正式代码/历史测试未改。

Dashboard来源为用户文字报告，代理未查看截图或读账户API；WorkersFree/DO零基线按 USER_REPORTED_DASHBOARD 接受，未来共享额度、实际部署权限和真实云端运行仍未验证。Plugin失败、CLI无凭据的历史没有删除；旧readonly OAuth方案已由Dashboard替代，未执行。

候选最终窗口：Brisbane 2026-11-16 09:00至11-17 09:00（UTC11-15 23:00至11-16 23:00），初始化09:00–09:20。两次部署/Secrets在最终窗口前完成；Stage1使用尚未持久化的准备窗口以读取identity，Stage2在初始化前切换最终配置。二者必须另批并核对hash；准备模式p51b-identity-prep和最终模式p51b-mock均已本地构建审计且保持禁用；实际激活/目标ID/Secret差异未来仍须审计。不得延长持久化期限；超时停止。完整方案见 gate_b_authorization_request.md。

Gate B执行阻断仍保留：明确批准未获；临近执行账户/名称/用量复核、真实URL/ID、bootstrap权限路径决策及cf粒度Token兼容性未验证。首次创建需产品级WorkersAdmin，不能声称只限新名称；不默认申请此权限。建议仅提交授权审阅，先由用户决定人工bootstrap/临时权限，不能立即部署。默认STOP_REVOKE_AND_RETAIN；删除另批。

'''
summary+='\n'.join(f'{k}: {v}' for k,v in zero.items())+'\nGATE_B_APPROVED: false\n\n---\n\n## 原始验收与账户调查历史（保留）\n\n'
initial=base['initial_user_files']['phase5_1b_cloudflare_remote_mock/gate_a_acceptance.md']
(OUT/'gate_a_acceptance.md').write_text(summary+initial)
# Recalculate preservation after replacing the current acceptance header.
assert all(content in (ROOT/n).read_text() for n,content in base['initial_user_files'].items())
changes=git('diff','--name-only').splitlines();new=git('ls-files','--others','--exclude-standard').splitlines()
handoff=f'''# Completion Handoff — Gate A Finalization

PHASE_5_1B_GATE_A_FINALIZATION: {'PASS' if passed else 'FAIL'}
READY_FOR_GATE_B_AUTHORIZATION_REVIEW: {str(passed).lower()}
GATE_B_APPROVED: false

1. Git HEAD `{protected_result['head']}`，未创建提交或推送。进入时已有两处tracked修改、三份untracked账户资料；原文在finalization_baseline.json中留存并全部包含于当前文件。仓库及检查的父目录未找到AGENTS.md，遵循本会话用户规则。当前工作区有本轮未提交修改；完整清单见下。
2. 仅修改Mock启动相关3个源码文件、2个既有测试、候选时间配置、构建runner/审计脚本，并新增2个测试辅助文件及Phase5.1B文档/证据。remote-worker.ts、正式Python规则、Phase4.2及Phase5.1/5.1A均未改。
3. 唯一SQLite事务包含窗口/预算/顺序/运行状态/完整checkpoint → 预算/执行记录 → Run+12 Claims → checkpoint与updated。Coordinator外层包装保留，内部组合方法要求持有Store事务，不产生嵌套事务。异常完整回滚，不清理旧状态或重建基线。
4. Node与本地workerd各19场景，6个语句执行后故障注入均快照一致、显式重试成功且预算只计1；另有事务所有权测试。所有启动测试collector=0，workerd outbound=0。完整TS281/281，原241保留；无跳过/删除。
5. Dashboard结果标USER_REPORTED_DASHBOARD：WorkersFree/US$0/每日100k、已有Worker1、候选无冲突、workers.dev已设、Cron0、DO namespace0及所报用量0。没有伪称CLI/API验证；精确时间和图表窗口、Workers已用量未提供。Plugin/CLI历史保留，无新认证。
6. Python271/271、TS281/281、Golden76、Yahoo32、11145数值字段差异0；两次完整合成24calls/26ticks；15类H02损坏请求前阻断；Kill/持久化/Alarm取消、本地workerd、typecheck、默认cf build、准备与最终两种remote dry-run均通过。Python初试4个TMPDIR路径错误留日志；项目级临时目录重跑通过，没有改历史代码。{len(protected)}个tracked保护文件hash一致，7条PENDING_REVIEW不变。
7. 资源名不变：Worker us-stocks-p51b-mock-20261113；SQLite RemoteMockCoordinator；实例phase51b-synthetic-20261113-v1。候选Brisbane11-16 09:00至11-17 09:00（UTC11-15 23:00至11-16 23:00），初始化09:00至09:20。两次部署在08:45前完成；Stage1尚未初始化时使用08:00准备窗口读取identity，Stage2改最终窗口，09:00后才初始化。20min不承担完整部署，错过则停止；不延长持久化截止。当前准备/最终两种配置均禁用且本地构建审计通过；将来获批后实际开启/ID/Secret差异还须核对配置hash。
8. 未来认证：推荐用户人工首次部署，后续仅单Worker Editor Token；metrics仅Metadata Read-Only。首次代理cf部署需要目标账户Workers产品级Admin，能影响已有Workers，必须单独选择/授权，不能默认申请。DO无独立角色、Secret权限不能细到单个名称；cf新粒度Token兼容性NOT_VERIFIED。推荐进程注入Token、无凭据文件；不读个人认证或Keychain。详见gate_b_authentication_plan.md。
9. 费用仅条件预计US$0，用户报告Free不等于零费用保证。共享余额会变、Workers used未知、公开无效请求/准备宽限/其他项目都消耗额度；真实CPU/Duration/SQL/Alarm仍PENDING_REMOTE_TEST。禁止升级和自动付费。
10. 默认STOP_REVOKE_AND_RETAIN：STOPPED、目标Alarm=null、导出证据、撤销应用Secrets及临时控制面授权，保留隔离资源。若关闭init flag需要第三次显式部署则不做，以删除init Secret+receipt防重放+截止失效并如实记录。FULL_CLEANUP_AFTER_REVIEW须另批精确目标/导出/删除权限与步骤，不能假设删除Worker即清除DO数据。
11. 剩余风险：GateB未批准；最终账户/URL/ID/新鲜用量待核；bootstrap与工具粒度兼容性待决；真实远程可靠性/资源创建和费用未验证。应用预算不是平台账单硬上限。没有进入Phase5.1C。
12. 建议提交GateB授权审阅，明确先决定认证bootstrap路径并核实执行权限；**不建议现在直接部署**。本任务完成后停止。

Source aggregate SHA256: `{build['reviewed_code_sha256']}`
Remote bundle SHA256: `{build['bundle_sha256']}` ({build['bundle_bytes']} bytes)

'''
handoff+='\n'.join(f'{k}: {v}' for k,v in zero.items())+'\nGATE_B_APPROVED: false\n\n## 当前工作区文件\n\n'
handoff+='\n'.join('- `'+n+'`' for n in sorted(set(changes+new+['phase5_1b_cloudflare_remote_mock/completion_handoff.md'])))+'\n'
(OUT/'completion_handoff.md').write_text(handoff)
print(json.dumps({'status':results['PHASE_5_1B_GATE_A_FINALIZATION'],'python':python['passed'],'typescript':counts['pass'],'protected':len(protected),'baseline_tests_retained':not missing,'gate_b_approved':False},ensure_ascii=False))
if not passed: raise SystemExit(1)
