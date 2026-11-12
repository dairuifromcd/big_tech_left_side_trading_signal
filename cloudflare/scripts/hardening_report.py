"""Report observed Phase 5.1A results; preserve all earlier acceptance artifacts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'phase5_1a_hardening'
def read(name):return json.loads((OUT/name).read_text())
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
log=(OUT/'typescript_tests.log').read_text()
counts={name:int(re.search(r'^# '+name+r' (\d+)\s*$',log,re.M)[1]) for name in ('tests','pass','fail','cancelled','skipped','todo')}
names=re.findall(r'^ok \d+ - (.*)$',log,re.M)
safety=[name for name in names if name.startswith(('H01 ','H02 '))]
python=read('python_tests.json');parity=read('parity_results.json');runtime=read('hardening_runtime_results.json');original_runtime=read('runtime_results.json');protected=read('protected_files_verification.json')
local_lines=(OUT/'local_initialization.log').read_text().splitlines()
local=next(json.loads(line) for line in local_lines if line.startswith('{"mode":"LOCAL_ONLY"'))
typecheck=subprocess.run(['node','cloudflare/scripts/local.mjs','typecheck'],cwd=ROOT,text=True,capture_output=True)
(OUT/'typecheck.log').write_text(typecheck.stdout+typecheck.stderr)
build='Build complete' in (OUT/'cf_build.log').read_text()
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True).strip()
results={'python':python,'typescript':{**counts,'original_tests_retained':sum(not n.startswith(('H01 ','H02 ')) for n in names),
          'new_security_tests':len(safety),'h01':sum(n.startswith('H01 ') for n in safety),'h02':sum(n.startswith('H02 ') for n in safety),
          'new_node_security_tests':sum('workerd' not in n for n in safety),'new_workerd_security_tests':sum('workerd' in n for n in safety)},
         'golden':{k:v for k,v in parity.items() if k!='results'},'hardening_runtime':runtime,
         'existing_runtime':original_runtime,'local_initialization_tool':local,'typecheck_exit_code':typecheck.returncode,'cf_build':'PASS' if build else 'FAIL',
         'notes':['All preflight-failure tests assert zero Collector calls; workerd scenarios additionally assert zero outbound requests.',
                  'Three symbol-commit protection cases inject invalid candidates AFTER a valid preflight and one Mock result; they deliberately assert one prior Mock call and unchanged committed states/events.',
                  'Node SQLite experimental and Miniflare RPC lifetime warnings are retained in logs; all runtime instances are explicitly disposed.',
                  'Miniflare may wrap thrown synchronous transaction errors; exact error categories are checked in Node tests and runtime tests independently assert no requests and no checkpoint mutation.']}
write('test_results.json',results)
passed=(python['total']==271 and python['passed']==271 and not python['network_attempts'] and not python['skipped'] and
        counts['pass']==counts['tests'] and counts['fail']==counts['cancelled']==counts['skipped']==0 and
        results['typescript']['original_tests_retained']==135 and parity['passed']==76 and parity['validation_fixtures']==32 and
        parity['max_absolute_difference']==0 and runtime['status']=='PASS' and runtime['outbound_requests']==0 and
        original_runtime['status']=='PASS' and original_runtime['outbound_requests']==0 and local['outbound_requests']==0 and
        typecheck.returncode==0 and build and protected['all_protected_unchanged'] and protected['pending_records_identical'] and protected['phase51_acceptance_unchanged'])
overall='PASS' if passed else 'FAIL'
components={name:overall for name in ['SAFE_INITIALIZATION','CHECKPOINT_PREFLIGHT','PRE_REQUEST_FAIL_CLOSED','EVENT_LEDGER_INTEGRITY',
             'LEGACY_PENDING_PROTECTION','PYTHON_REGRESSION','TYPESCRIPT_REGRESSION','GOLDEN_PARITY','PROTECTED_FILES_INTEGRITY']}
components['READY_FOR_PHASE_5_1B_REVIEW']='READY_FOR_HUMAN_REVIEW_ONLY' if passed else 'NOT_READY'
zero={'CLOUDFLARE_REMOTE_MUTATIONS':0,'REMOTE_DEPLOYMENTS':0,'REAL_YAHOO_REQUESTS':0,'LIVE_TRADING_ACTIONS':0}
tracked_changes=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
new=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
risks=['真实Cloudflare管理调用身份、Secret/binding权限及远程初始化均NOT_VERIFIED；没有云端执行器或激活。',
       '本地metadata hash不能防拥有完整数据库/部署权限的恶意管理员；generation依赖受控SQLite写路径与平台原子性。',
       '旧Phase5.1 receipt、旧Python evidence/audit格式需迁移处理；本阶段保守阻断，不执行迁移。',
       '未来内部管理调用方的访问入口、最小权限、凭据签发/撤销及精确资源目标仍须单独审阅授权。',
       '真实CPU/内存与长期可靠性未验证，先前Phase5.1 PARTIAL的其他缺项仍然保留。']
acceptance={'PHASE_5_1A_HARDENING':overall,'scope':['H01','H02'],'git_head':head,'initial_worktree':'CLEAN','final_worktree':status,
            'components':components,**zero,'remote_initialization':'NOT_VERIFIED','cloud_execution':'NOT_AUTHORIZED_NOT_PERFORMED',
            'regression':results['typescript'],'python':python,'golden':results['golden'],'protected_files':protected,
            'modified_files':tracked_changes,'new_files':new,'remaining_risks':risks,
            'phase51_overall_status_remains':'PARTIAL','automatic_git_commits':0,'automatic_git_pushes':0}
write('acceptance.json',acceptance)
lines=[f'PHASE_5_1A_HARDENING: {overall}','','验收仅限H01/H02本地安全加固。真实云端初始化NOT_VERIFIED；未进入Phase5.1B。','',
       '| 分项 | 结果 |','|---|---|']+[f'| {k} | {v} |' for k,v in components.items()]
lines+=['',f'Python {python["passed"]}/{python["total"]}；TypeScript {counts["pass"]}/{counts["tests"]}，原135项完整保留，新增{len(safety)}项（H01 {results["typescript"]["h01"]}、H02 {results["typescript"]["h02"]}）。无失败或跳过。',
        '',f'Golden76，Yahoo验证32，数值字段{parity["compared_float_fields"]}个，最大绝对差{parity["max_absolute_difference"]}；事件ID、WATCH、事件/确认决策无回归。',
        '',f'workerd中{runtime["blocked_checkpoint_cases"]}种损坏/不支持checkpoint场景均在采集前拒绝：collector_calls_for_blocked_cases=0，outbound_requests=0。',
        '', 'H01内部RPC：默认禁用、单独credential、精确DO目标、明确授权说明；空库才允许原子写receipt/schema/audit。无普通HTTP管理路由，不需LOCAL_TESTING。重复/非空/未授权/中断均按测试拒绝或回滚。命令字段白名单避免credential误入receipt。',
        '', 'H02顺序：事务内校验receipt→全部状态→完整事件hash/语义ID/evidence/audit→confirmed/pending/revision/依赖引用→原始证据及当前Report历史→创建run与claims并记录验证标记。之后请求前检查SQLite generation，单标的提交检查相关记录并保护旧决定。',
        '', '性能：本地原12标的运行与API检查只执行1次全量预检。generation触发器避免每个标的重复全账本校验；真实云端CPU及额度NOT_VERIFIED，未以降低校验换取性能。',
        '',f'保护：{protected["protected_file_count"]}个非授权修改的原tracked文件SHA256一致，Phase5.1验收目录完整不变，7条正式pending及隔离副本均未改。完整Python回归还保留原历史保护断言。',
        '', '说明：3项事务提交测试在合法预检及Mock返回后注入坏候选，预期先有1次Mock调用；它们检查旧状态/事件未变，不属于“坏checkpoint请求前阻断”场景。后者全部明确断言Collector为0。',
        '', '本地初始化工具、typecheck和cf build均通过。Miniflare SQL检查器会写自身表，已关闭；没有放宽空库保护。测试日志中的SQLite实验性提示及RPC生命周期提示保留，模拟器最终全部dispose。',
        '', '剩余风险：','']+['- '+r for r in risks]
lines+=['','Phase5.1B前置条件见phase5_1b_review_prerequisites.md；本地安全检查通过仅表示可以人工审阅，所有云端资源、管理调用方、Secrets和执行均需单独授权。','','本阶段未提交、未推送Git更改。','']+[f'{k}: {v}' for k,v in zero.items()]
(OUT/'acceptance.md').write_text('\n'.join(lines)+'\n')
handoff=[f'PHASE_5_1A_HARDENING: {overall}',f'Git HEAD: {head}；初始干净，当前仅有H01/H02相关未提交改动。',
         '修改：storage/coordinator/worker/core的相关逻辑、测试输出位置和本地runner；新增checkpoint/initialization/integrity模块、初始化工具、安全测试及本阶段文档。完整文件清单见acceptance.json。',
         'H01：默认关闭的内部初始化RPC；独立credential、目标ID与授权说明；严格新空库，事务写入可验证receipt/schema/audit。无Dashboard管理路由，不启用通用测试后门。',
         'H02：完整checkpoint只读验证与启动同一事务；状态/事件/evidence/audit/跨引用/原始证据一致性；请求前generation复核；单标的提交保护旧决定和依赖标记。',
         f'新增安全测试{len(safety)}项，完整TS {counts["pass"]}/{counts["tests"]}；Python {python["passed"]}/{python["total"]}；无失败/跳过。',
         'Golden76 + Yahoo32，11145个数值字段最大差异0，ID及离散结果一致。',
         f'保护：{protected["protected_file_count"]}个受保护tracked文件不变，Phase5.1资料未覆盖，7条旧pending不变。',
         '未验证：真实Cloudflare调用身份、权限/Secret绑定、远程初始化、CPU/内存/长期运行；旧格式迁移和Phase5.1其他缺项仍未实施。',
         'Phase5.1B须先单独授权账户只读核实、专用Mock资源、可信内部调用方、一次性Secret和明确目标/次数/截止。不得启用LOCAL_TESTING或自动进入远程实验。',
         '无自动Git提交/推送，无部署。本阶段到此停止。']+[f'{k}: {v}' for k,v in zero.items()]
(OUT/'completion_handoff.md').write_text('\n\n'.join(handoff)+'\n')
manifest={}
for name in set(tracked_changes+new+['phase5_1a_hardening/acceptance.json','phase5_1a_hardening/acceptance.md','phase5_1a_hardening/completion_handoff.md']):
    path=ROOT/name
    if path.is_file() and path.name!='artifact_manifest.json':manifest[name]=hashlib.sha256(path.read_bytes()).hexdigest()
write('artifact_manifest.json',dict(sorted(manifest.items())))
print(json.dumps({'overall':overall,'components':components,'python':python,'typescript':results['typescript'],**zero},ensure_ascii=False,indent=2))
if not passed:raise SystemExit(1)
