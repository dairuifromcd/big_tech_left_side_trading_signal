"""Offline regression + isolated nine-stock state-safety acceptance."""
import ast
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import unittest

from src import monitor,state
from diagnostics.analyze_adjclose_revisions import current_tolerances

ROOT=monitor.ROOT


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def old_test_ids():
    base=ROOT/'phase4_1_1_trial/baseline/snapshot/tests'
    found=set()
    for path in list(base.glob('test*.py'))+list(ROOT.glob('test*.py')):
        module='tests.'+path.stem if path.parent==base else path.stem
        tree=ast.parse(path.read_text())
        for cls in tree.body:
            if isinstance(cls,ast.ClassDef):
                found.update(module+'.'+cls.name+'.'+fn.name for fn in cls.body if isinstance(fn,ast.FunctionDef) and fn.name.startswith('test_'))
    return found


def main():
    attempts=[]
    def offline(event,args):
        if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','http.client.connect','urllib.Request'):
            attempts.append(event);raise RuntimeError('Phase4.1.1 forbids network: '+event)
    sys.addaudithook(offline)
    base=ROOT/'phase4_1_1_trial/baseline';manifest=json.loads((base/'manifest.json').read_text())
    run=ROOT/'phase4_1_1_trial'/('acceptance_'+dt.datetime.now(monitor.phase2.BRISBANE).strftime('%Y%m%d_%H%M%S'))
    run.mkdir()
    outcomes=[]
    class Recorder(unittest.TextTestResult):
        def addSuccess(self,test):super().addSuccess(test);outcomes.append({'id':test.id(),'status':'PASS'})
        def addFailure(self,test,err):super().addFailure(test,err);outcomes.append({'id':test.id(),'status':'FAIL'})
        def addError(self,test,err):super().addError(test,err);outcomes.append({'id':test.id(),'status':'ERROR'})
    log=io.StringIO();tests=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Recorder).run(unittest.defaultTestLoader.discover(str(ROOT)))
    (run/'tests.txt').write_text(log.getvalue())
    (run/'tests.json').write_text(json.dumps({'total':tests.testsRun,'failures':len(tests.failures),'errors':len(tests.errors),'skipped':len(tests.skipped),'outcomes':outcomes},indent=2)+'\n')
    if not tests.wasSuccessful():print(log.getvalue());return 1
    old=old_test_ids();passed={r['id'] for r in outcomes if r['status']=='PASS'}
    assert len(old)==133 and old.issubset(passed) and not tests.skipped
    checkpoint=run/'state.json';shutil.copyfile(ROOT/'state/monitor_state.json',checkpoint)
    migration=state.migrate_path(checkpoint);migrated=digest(checkpoint)
    assert not state.migrate_path(checkpoint)['changed'] and migrated==digest(checkpoint)
    p2=monitor.run(state_path=checkpoint,output_dir=run/'phase2')
    prior=json.loads((ROOT/'phase4_trial/acceptance.json').read_text())
    live=json.loads((ROOT/prior['live_report']).read_text())
    p4=monitor.run(Path(live['input_file']),checkpoint,run/'phase4')
    before=digest(checkpoint);repeat=monitor.run(Path(live['input_file']),checkpoint,run/'repeat')
    assert before==digest(checkpoint) and not repeat['state_updated']
    assert all(s['change_event']=='NO_CHANGE' for s in repeat['stocks'])
    count=sum(s['historical_revision_count'] for s in p4['stocks'])
    assert count==1139 and p2['success_count']==p4['success_count']==9 and not p4['new_observation_events']
    for row in p4['stocks']:
        previous=next(s for s in live['stocks'] if s['symbol']==row['symbol'])
        for key in ('adjclose','highest_adjclose','highest_date','drawdown','rsi14','sma50','sma200','watch_tier'):
            assert row[key]==previous[key],(row['symbol'],key)
    current=state.load(checkpoint);state.validate_v2(current)
    pending=[e for e in current['event_records'].values() if e['status']=='PENDING_REVIEW']
    assert len(pending)==12 and len(migration['ambiguous_thresholds'])==11
    protected={p:digest(ROOT/p)==h for p,h in manifest['protected_sha256'].items()};assert all(protected.values())
    assert digest(ROOT/'src/indicators.py')==manifest['source_sha256']['src/indicators.py']
    assert current_tolerances()=={'abs_tol':1e-8,'rel_tol':1e-10}
    unchanged_core={str(p):digest(ROOT/p)==manifest['source_sha256'][p] for p in ('src/indicators.py','src/signals.py')}
    assert all(unchanged_core.values())
    scenario_results={}
    for group in ('U','M','C'):
        for n in range(1,6):
            code=group+str(n);matches=[r for r in outcomes if r['id'].startswith('tests.test_phase4_1_1.') and '.test_'+code.lower()+'_' in r['id']]
            assert matches and all(r['status']=='PASS' for r in matches)
            scenario_results[code]={'status':'PASS','tests':[r['id'] for r in matches]}
    acceptance={k:'PASS' for k in ('REVISION_RISK_ESCALATION','PENDING_REVIEW_INTEGRITY','MISSING_STATE_FAIL_CLOSED',
                'EXPLICIT_INITIALIZATION','MISSED_SESSION_DETECTION','EVENT_LEDGER_IDEMPOTENCY','EXISTING_REGRESSION_TESTS',
                'INDICATORS_UNCHANGED','FORMAL_STATE_UNCHANGED','PROTECTED_EVIDENCE_UNCHANGED')}
    acceptance['CATCHUP_SAFETY']='BLOCKED'
    acceptance['PHASE_4_1_1_ACCEPTANCE']='PASS'
    acceptance['CROSS_DAY_LIVE_VALIDATION']='PENDING_LIVE_VALIDATION'
    categories={}
    for row in outcomes:
        category=row['id'].split('.')[1] if row['id'].startswith('tests.') else row['id'].split('.')[0]
        entry=categories.setdefault(category,{'total':0,'passed':0,'failed':0})
        entry['total']+=1;entry['passed']+=row['status']=='PASS';entry['failed']+=row['status']!='PASS'
    report={'phase':'4.1.1','mode':'OFFLINE_STATE_SAFETY_PATCH','at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'new_http_requests':0,'network_attempts_blocked':attempts,'acceptance':acceptance,
        'acceptance_scope':'Requested fail-closed state-safety patch PASS; automatic reconstructed catchup remains BLOCKED. Not complete unattended recovery capability.',
        'baseline':{'tests':json.loads((base/'tests.json').read_text()),'manifest':str(base/'manifest.json'),
                    'pre_fix_failures':str(base/'pre_fix_failures.txt'),'git_commit':None,'git_status':'Untracked working files preserved in source snapshot'},
        'tests':{'total':tests.testsRun,'passed':tests.testsRun,'failed':0,'skipped':0,'existing_133_passed':len(old),'new_tests':tests.testsRun-len(old),
                 'old_test_ids_retained':sorted(old),'categories':categories,'test_results':str(run/'tests.json'),'log':str(run/'tests.txt')},
        'scenarios':scenario_results,
        'defects_and_fixes':[
            {'defect':'Existing revision ID kept CONFIRMED despite new higher-risk evidence','fix':'Only new REVISION_OBSERVATION evidence with explicit requires_review escalates to pending; evidence versions, risk audit and references commit together.'},
            {'defect':'Missing file implicitly became empty state','fix':'Strict load/save default. Explicit init only in a new existing isolated directory; prior backup/initialization/recovery artifacts block reset. Recovery is operator-selected and audited.'},
            {'defect':'Nonconsecutive sessions could still advance successful date','fix':'Per-symbol missing-session plan and CATCHUP_REQUIRED preserves checkpoint; other stocks can continue. Read-only RECONSTRUCTED_CATCHUP plan blocks automatic application.'}],
        'modified_files':['src/state.py','src/monitor.py','src/observations.py','src/review.py','src/phase4.py','README.md','tests/test_phase3.py','tests/test_phase4_1.py','tests/test_phase4_1_guardrails.py'],
        'new_files':['src/catchup.py','tests/test_phase4_1_1.py','diagnostics/validate_phase4_1_1.py'],
        'existing_test_updates':[
            'Phase3 IntegrationTests explicitly initialize each fresh temporary checkpoint before normal runs; all original baseline/byte-idempotence assertions remain.',
            'Phase4.1 fixture creation uses explicit initialize(value) instead of save() implicitly creating a missing file. No old test deleted/skipped or expectation weakened.',
            'Phase4 replay explicitly initializes its newly requested isolated replay state; replay is not live monitoring.'],
        'integration':{'state_file':str(checkpoint),'phase2_report':p2['report_file'],'phase4_report':p4['report_file'],'repeat_report':repeat['report_file'],
                       'retained_revisions':count,'pending_records':len(pending),'legacy_ambiguities':11,'false_market_events':0,
                       'metrics_equal_original_phase4':True,'repeat_state_byte_identical':True,'state_sha256':before,
                       'stocks':[{k:r[k] for k in ('symbol','adjclose','drawdown','rsi14','sma50','sma200','watch_tier','data_quality','historical_revision_count')} for r in p4['stocks']]},
        'state_schema':2,'event_model_version':state.EVENT_MODEL_VERSION,'formal_migration_performed':False,
        'formal_state_sha256':digest(ROOT/'state/monitor_state.json'),'protected_evidence_count':len(protected),'protected_evidence_unchanged':all(protected.values()),
        'unchanged_core':unchanged_core,'revision_tolerances':current_tolerances(),
        'production_code_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'src').glob('*.py'))},
        'manual_recovery_commands':[
            '.venv/bin/python -m src.review --state ISOLATED/state.json --list-backups',
            '.venv/bin/python -m src.phase4 --state ISOLATED/state.json --recover-backup SELECTED_VERIFIED_BACKUP.json',
            '.venv/bin/python -m src.review --state ISOLATED/state.json --catchup-plan --input SAVED_PRICES.json',
            '.venv/bin/python -m src.monitor --state ISOLATED/state.json --input ORIGINAL_ARCHIVED_DAY.json --archived-catchup --archive-attestation "Verified original capture and source hashes" --output-dir ISOLATED/reports'],
        'limitations':['No automatic backfill/reconstruction. Later adjusted histories do not establish historical Point-in-Time snapshots.',
                       'Original archive capture timestamps and hashes are local evidence, not independently authenticated; operator must verify trust.',
                       'Backup rollback may restore earlier event decisions; reconcile stable event IDs before future external delivery.',
                       'Yahoo remains single source; SPCX dispute and live cross-day verification remain unresolved.',
                       'No live requests, scheduled jobs, external delivery, trading, formal migration or Phase5 performed.']}
    output=ROOT/'reports/phase4_1_1_patch_validation.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Phase 4.1.1 状态安全修补验收','',f"全阶段离线；{tests.testsRun}/{tests.testsRun}测试通过，原有133项全部保留通过，新测试{tests.testsRun-133}项；无跳过。",'',
           '状态安全修补范围验收PASS；**自动重建补跑仍BLOCKED，不能据此宣称完整无人值守恢复能力。**','',
           '## 缺陷与修补','']
    lines += ['- '+r['defect']+' → '+r['fix'] for r in report['defects_and_fixes']]
    lines += ['', '同一修订ID保留全部证据，风险升级独立记入audit及review_history；pending不自动降低，REJECTED新证据安全阻断。已确认市场事件不撤销，只追加明确依赖风险；复核解除风险也留痕。',
              '普通监控与辅助命令默认严格读取；--init-state是明确意图，需现存空白隔离目录。初始化收据及备份阻止通过删除主文件重建基线。缺失主文件列出经过完整校验的备份，不自动选取；恢复记录回滚风险。','',
              '## 场景回归','', '| 场景 | 结果 |','|---|---|']
    lines += ['| '+code+' | '+value['status']+' |' for code,value in scenario_results.items()]
    lines += ['', 'C2/C5使用固定、逐日、无未来价格的合成档案验证明确手工推进和中断恢复，不作为历史真实Point-in-Time行情认证。C3只产生RECONSTRUCTED_CATCHUP/PENDING_REVIEW只读计划，或拒绝与原始采集时间不符的回填输入，不改写旧状态。',
              '', '## 完整回归','', '| 类别 | 总数 | 通过 | 失败 |','|---|---:|---:|---:|']
    lines += [f"| {k} | {v['total']} | {v['passed']} | {v['failed']} |" for k,v in categories.items()]
    lines += ['', '旧测试只将隐式创建夹具改为显式初始化；精确状态保护与数学断言保持。补丁前U1/M1/C1失败证据已保存。',
              '', '## 九股隔离集成','', '1,139条历史修订、11条迁移歧义及共12条待复核完整保留；无虚假市场事件。九股全部指标、高点日期和WATCH档位逐项等于原Phase4，SPCX为PASS_PROVISIONAL。重复行情字节级幂等。',
              '', '## 受保护状态','',f"正式状态SHA256：`{report['formal_state_sha256']}`；{len(protected)}份既有证据/状态文件哈希完全不变。无正式迁移。",'',
              '## 文件','']
    lines += ['- 修改：'+s for s in report['modified_files']]+['- 新增：'+s for s in report['new_files']]
    lines += ['', '## 人工恢复路径','']+['- `'+s+'`' for s in report['manual_recovery_commands']]
    lines += ['', '先保存检查点与账本；只选择通过验证的备份。补跑必须逐日提供有可信原始采集记录的完整档案，检查每日报告后再处理下一天；无法取得时保持阻断，不能改日期或删除状态绕过。',
              '', '## 验收','']+['- '+k+': '+v for k,v in acceptance.items()]
    lines += ['', '## 未覆盖风险与限制','']+['- '+s for s in report['limitations']]
    (ROOT/'reports/phase4_1_1_patch_validation.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'report':str(output),'tests':tests.testsRun,'acceptance':acceptance},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
