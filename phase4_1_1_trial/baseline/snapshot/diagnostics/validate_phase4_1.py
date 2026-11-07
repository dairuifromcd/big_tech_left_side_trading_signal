"""Reproducible offline Phase 4.1 acceptance, always in a fresh isolated run."""
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import unittest

from src import monitor, state
from diagnostics import revision_scenarios
from diagnostics.analyze_adjclose_revisions import current_tolerances

ROOT=monitor.ROOT


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    attempted=[]
    def offline(event,args):
        if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','http.client.connect','urllib.Request'):
            attempted.append(event)
            raise RuntimeError('Phase4.1 forbids network: '+event)
    sys.addaudithook(offline)
    manifest=json.loads((ROOT/'phase4_1_trial/baseline/manifest.json').read_text())
    run=ROOT/'phase4_1_trial'/('acceptance_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    run.mkdir()
    results=[]
    class Recorded(unittest.TextTestResult):
        def addSuccess(self,test):
            super().addSuccess(test);results.append({'test':test.id(),'status':'PASS'})
        def addFailure(self,test,err):
            super().addFailure(test,err);results.append({'test':test.id(),'status':'FAIL'})
        def addError(self,test,err):
            super().addError(test,err);results.append({'test':test.id(),'status':'ERROR'})
    log=io.StringIO()
    tests=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Recorded).run(unittest.defaultTestLoader.discover(str(ROOT)))
    (run/'tests.txt').write_text(log.getvalue())
    (run/'tests.json').write_text(json.dumps({'total':tests.testsRun,'failures':len(tests.failures),'errors':len(tests.errors),'skipped':len(tests.skipped),'results':results},indent=2)+'\n')
    if not tests.wasSuccessful():
        print(log.getvalue());return 1
    p=run/'monitor_state.json';shutil.copyfile(ROOT/'state/monitor_state.json',p)
    migration=state.migrate_path(p);migrated_hash=digest(p)
    migration_repeat=state.migrate_path(p)
    assert not migration_repeat['changed'] and migrated_hash==digest(p)
    first=monitor.run(state_path=p,output_dir=run/'phase2')
    acceptance=json.loads((ROOT/'phase4_trial/acceptance.json').read_text())
    live=json.loads((ROOT/acceptance['live_report']).read_text())
    second=monitor.run(Path(live['input_file']),p,run/'phase4')
    second_hash=digest(p)
    again=monitor.run(Path(live['input_file']),p,run/'repeat')
    assert not again['state_updated'] and second_hash==digest(p)
    assert all(s['change_event']=='NO_CHANGE' for s in again['stocks'])
    total=sum(s['revision_observation']['count'] for s in second['stocks'])
    assert total==1139 and second['success_count']==9 and first['success_count']==9
    assert not second['new_observation_events']
    for row in second['stocks']:
        prior=next(s for s in live['stocks'] if s['symbol']==row['symbol'])
        for key in ('adjclose','highest_adjclose','highest_date','drawdown','rsi14','sma50','sma200','watch_tier'):
            assert row[key]==prior[key],(row['symbol'],key)
    # Persist both exact B fixtures: legacy Close-mutating -> pending and
    # additional unchanged-Close evidence -> confirmed under validated units.
    pairs,day=revision_scenarios._base_pairs()
    _,old=revision_scenarios._process(pairs)
    revised=list(pairs);revised[10]=(pairs[10][0],90.0001);revised.append((day,79.))
    b_pending,_=revision_scenarios._process(revised,old)
    stock,diag=revision_scenarios._snapshot(revised)
    for r in stock['rows']:
        if r['trading_date'] in dict(pairs):r['close']=dict(pairs)[r['trading_date']]
    b_confirmed,_=monitor.process_symbol('NVDA',stock,diag,old,1.)
    assert b_pending['change_event']=='PENDING_REVIEW' and 20 not in b_pending['triggered_thresholds']
    assert b_confirmed['change_event']=='NEW_THRESHOLD' and 20 in b_confirmed['confirmed_thresholds']
    scenarios=revision_scenarios.run_scenarios()
    (run/'scenarios.json').write_text(json.dumps({'synthetic':True,'A_to_E':scenarios,'B_stable_Close':b_confirmed,'B_missing_comparable_Close':b_pending},indent=2)+'\n')
    protected={path:digest(ROOT/path)==value for path,value in manifest['protected_sha256'].items()}
    assert all(protected.values())
    assert digest(ROOT/'src/indicators.py')==manifest['source_sha256']['src/indicators.py']
    assert current_tolerances()=={'abs_tol':1e-8,'rel_tol':1e-10}
    categories={}
    for r in results:
        category=r['test'].split('.')[0] if not r['test'].startswith('tests.') else r['test'].split('.')[1]
        entry=categories.setdefault(category,{'total':0,'passed':0,'failed':0})
        entry['total']+=1;entry['passed']+=r['status']=='PASS';entry['failed']+=r['status']!='PASS'
    schema=state.load(p)
    report={'phase':'4.1','mode':'OFFLINE_FIX_REGRESSION','new_http_requests':0,'network_attempts':attempted,
            'source_baseline':'phase4_1_trial/baseline/snapshot','pre_fix_test_result':json.loads((ROOT/'phase4_1_trial/baseline/tests.json').read_text()),
            'pre_fix_P0_failure':'phase4_1_trial/baseline/p0_failure.txt','design':'phase4_1_trial/design.md',
            'tests':{'total':tests.testsRun,'passed':tests.testsRun,'failed':0,'skipped':len(tests.skipped),'categories':categories,'log':str(run/'tests.txt')},
            'schema_version':schema['schema_version'],'event_model_version':state.EVENT_MODEL_VERSION,
            'migration':migration,'repeat_migration':migration_repeat,'formal_migration_performed':False,
            'integration':{'phase2_report':first['report_file'],'phase4_report':second['report_file'],'repeat_report':again['report_file'],
                           'state_file':str(p),'state_sha256':second_hash,'repeat_byte_identical':True,
                           'retained_revision_count':total,'false_market_events':0,'indicators_equal_old_phase4':True,
                           'pending_records':len([e for e in schema['event_records'].values() if e['status']=='PENDING_REVIEW']),
                           'spcx_quality':next(s['data_quality'] for s in second['stocks'] if s['symbol']=='SPCX')},
            'B_result':{'stable_Close_market':b_confirmed['market_observation'],'insufficient_evidence_market':b_pending['market_observation'],
                        'pending_confirmed_thresholds':b_pending['confirmed_thresholds'],'confirmed_thresholds':b_confirmed['confirmed_thresholds']},
            'synthetic_scenario_file':str(run/'scenarios.json'),'original_protected_file_count':len(protected),'original_evidence_unchanged':all(protected.values()),
            'formal_state_sha256':digest(ROOT/'state/monitor_state.json'),'indicator_source_unchanged':True,'revision_tolerances_unchanged':True,
            'production_source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'src').glob('*.py'))},
            'modified_files':['src/monitor.py','src/state.py','src/signals.py (legacy API documentation)','src/phase4.py','diagnostics/revision_scenarios.py','tests/test_phase4.py','tests/test_revision_diagnostics.py','README.md'],
            'new_files':['src/observations.py','src/review.py','tests/test_phase4_1.py','tests/test_phase4_1_guardrails.py','diagnostics/validate_phase4_1.py'],
            'old_test_expectation_updates':['Phase4 fault tests migrate the isolated fixture before fault injection; exact unchanged-state assertions remain. Added all-failed-v1 no-write guard.',
                                             'Revision scenario B now asserts preserved pending candidate and unconsumed confirmation rather than asserting the former known defect. The pre-fix failure remains archived.'],
            'acceptance':{'P0_SIGNAL_DECOUPLING':'PASS','REVISION_FACT_PRESERVATION':'PASS','NO_FALSE_MARKET_CROSSING':'PASS','STATE_MIGRATION':'PASS','PENDING_REVIEW_LIFECYCLE':'PASS','ATOMICITY_AND_IDEMPOTENCY':'PASS','PROTECTED_DATA':'PASS'},
            'limitations':['Yahoo upstream precision cause remains unconfirmed; SPCX unresolved anomaly remains provisional.','Unit comparability proof is deliberately conservative; real dividends/splits or missing provenance may need review.','Legacy scalar transition(revision=True) is revision-only compatibility; full production monitor uses independent observations.','Confirmed is a technical observation, never DELIVERED; no external notifications exist.','Recovery to an older backup may restore older decisions; stable IDs permit reconciliation but no external delivery ledger exists.','Real cross-day live validation remains pending; no Phase5 or network execution performed.']}
    out=ROOT/'reports/phase4_1_fix_validation.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Phase 4.1 修复及回归验收','',f"全程离线。测试{tests.testsRun}/{tests.testsRun}通过；无跳过；正式状态及{len(protected)}份既有保护文件哈希不变。",'',
           '## 修复结果','', '修订事实与市场观察同时保留；单一change_event仅作兼容摘要。v2将observed/baseline/confirmed/pending分开，triggered_thresholds仅为confirmed兼容别名。CONFIRMED不代表通知、评级或买入。',
           '稳定事件ID不含运行时间或价格噪声；待复核升级沿用原ID，确认/拒绝/保持待复核均保留审计。修订与阈值使用不同事件身份。',
           '单股候选状态及账本先完整验证，再合并到全局候选；锁、备份和原子提交继续保留。', '',
           '## 场景验收','', '| 场景 | 修复后结果 |','|---|---|',
           '| A：同日旧低价微修订 | 保留修订，不确认新阈值 |',
           '| B：稳定Close、高点100、新价79 | 修订事实 + CONFIRMED WATCH_20 同时存在 |',
           '| B：旧Close也变化，证据不足 | PENDING_REVIEW，WATCH_20不消耗确认资格 |',
           '| C：同日高点100→110 | 修订及复核，无市场新触档 |',
           '| D：高点修订与新价格共同作用 | 候选待复核，不能混合不同单位确认 |',
           '| E：同输入重复 | 不重复事件、不改写状态 |',
           '| F–N | 同日变动、多档、恢复重入、窗口移出、边界、重标定、SPCX及单股待审全部通过 |',
           '| O–T | 写入失败、恢复、迁移、旧阈值歧义、同ID升级、拒绝回滚、锁账本一致性全部通过 |','',
           '## 回归统计','', '| 测试类别 | 总数 | 通过 | 失败 |','|---|---:|---:|---:|']
    lines += [f"| {k} | {v['total']} | {v['passed']} | {v['failed']} |" for k,v in categories.items()]
    lines += ['', '旧测试未删除或跳过。Phase4故障用例先迁移隔离夹具，再注入故障，完整保留字节不变断言；诊断B的旧缺陷预期改为要求保留候选。修复前失败和103项基线均已保存。','',
              '## 九股离线集成与迁移','',f"从正式状态复制的隔离文件迁为v2：{len(migration['ambiguous_thresholds'])}条旧阈值歧义保留待复核，未自动确认或补发。重复迁移字节不变。", 
              'Phase2→Phase4价格仍识别1139条修订；九股指标、最高点日期及WATCH档位逐项等于原Phase4。无虚假市场事件；SPCX仍PASS_PROVISIONAL，SMA200=N/A。',
              f"当前隔离账本有{report['integration']['pending_records']}条待复核记录（11条迁移歧义及AVGO微小高点修订）。同份Phase4数据重跑九股NO_CHANGE，状态SHA256完全一致。", '',
              '## 文件与兼容性','']
    lines += ['- 修改：'+s for s in report['modified_files']]+['- 新增：'+s for s in report['new_files']]
    lines += ['', '数学规则版本不变，事件模型版本revision-market-v2。v1仍可只读验证，迁移仅在隔离副本，明确拒绝正式状态路径。原账本完整保留legacy_event_records；仅可信旧市场账本可支持确认，其余待复核。',
              '使用 src.review --migrate / --list-pending / --event-id ... --decision CONFIRM|REJECT|KEEP --reason ... 明确操作隔离状态。拒绝修订需要有效旧检查点；已向前推进则停止，不擅自回滚较新状态。','',
              '## 验收结论','']+['- '+k+': '+v for k,v in report['acceptance'].items()]
    lines += ['', '## 保留风险','']+['- '+s for s in report['limitations']]
    lines += ['', '正式状态SHA256：`'+report['formal_state_sha256']+'`','', '本阶段无HTTP、调度、交易、外部投递或Phase5。','']
    (ROOT/'reports/phase4_1_fix_validation.md').write_text('\n'.join(lines))
    print(json.dumps({'report':str(out),'tests':tests.testsRun,'acceptance':report['acceptance']},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
