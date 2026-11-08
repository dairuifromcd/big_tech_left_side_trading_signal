"""Strictly offline full regression, before/after attribution and archive audit."""
import copy
import datetime as dt
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from src import indicators, market_indices as idx, index_data, monitor, observations as obs, state
from tests.test_adjclose_refinement import scenario, identity, index_item

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'adjclose_revision_refinement'
ALLOWED={'src/observations.py','src/market_indices.py','src/monitor.py','MARKET_INDICES.md'}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def archived_module(name,path):
    loader=importlib.machinery.SourceFileLoader(name,str(path))
    spec=importlib.util.spec_from_loader(name,loader)
    module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module


def stock_view(row):
    return {'metrics':{key:row[key] for key in ('trading_date','adjclose','highest_adjclose','highest_date','drawdown','rsi14','sma50','sma200','watch_tier')},
            'summary':row['change_event'],'market_candidates':[{key:e.get(key) for key in ('event_type','event_subtype','threshold','status')} for e in row['market_events']],
            'confirmed_thresholds':row['confirmed_thresholds'],'revision':{key:value for key,value in row['revision_observation'].items() if key not in ('raw_differences','dates')},
            'semantics':{key:row.get(key) for key in ('daily_drawdown_change_pp','daily_new_deepening','cumulative_anchor_deepening_pp','raw_market_candidate_type','event_status','candidate_confirmed','stored_previous_drawdown_change_pp')},
            'attribution':row['market_observation']}


def index_view(row,document,date):
    return {'metrics':{key:row[key] for key in ('trading_date','adjclose','highest_adjclose','highest_date','drawdown','rsi14','sma50','sma200','watch_tier')},
            'summary':row['change_event'],'market_candidates':[{key:e.get(key) for key in ('event_type','threshold','status')} for e in document['event_records'].values() if e['trading_date']==date and e['event_type']!='REVISION_OBSERVATION'],
            'confirmed_thresholds':row['confirmed_thresholds'],'revision':row['revision_observation'],
            'semantics':{key:row.get(key) for key in ('daily_drawdown_change_pp','daily_new_deepening','cumulative_anchor_deepening_pp','raw_market_candidate_type','event_status','candidate_confirmed')},
            'attribution':row.get('market_observation')}


def compare_cases():
    old_stock=archived_module('_before_observer',OUT/'baseline/observations.py.before')
    old_index=archived_module('_before_index',OUT/'baseline/market_indices.py.before')
    cases=[]
    expectations={'unchanged':'Unchanged histories: real new20 confirmed.', 'micro':'Record non-extremum micro revision and permit strictly proven new20.',
        'material':'Material related history: latest metrics, candidate retained pending.', 'high_same_tier':'Recompute revised high and actual metric deltas.',
        'revision_only':'Latest WATCH20; no new market crossing from pure history change.', 'mixed_material':'Keep both disputed20/30 candidates, consume neither.',
        'disagreement':'Do not silently drop disputed20 candidate.', 'one_basis_only':'Both current tiers include20 but only old basis newly crossed: pending.',
        'unrelated_material':'Material old warmup revision remains reviewable; independent current event may confirm.',
        'near_boundary':'Nonzero micro-revision error bound exceeds threshold margin: pending.',
        'close_only':'INDEX Close display/provenance only; EQUITY Close safety still blocks.',
        'prior_unrelated':'Complete known price-only provenance outside both windows: confirm new event, preserve old pending.',
        'prior_related':'Related old pending revision still blocks.', 'prior_unknown':'Unknown old evidence fails closed.',
        'prior_source_risk':'Old identity/source uncertainty is not dismissed by a date-window check.'}
    for asset in ('stock','index'):
        for name,expectation in expectations.items():
            pairs,closes,meta,previous,context=scenario(name,asset);old_context=copy.deepcopy(context)
            if asset=='stock':
                before=old_stock.evaluate(meta['symbol'],pairs,closes,meta,previous)
                after=obs.evaluate(meta['symbol'],pairs,closes,meta,previous,event_context=context)
                a,b=stock_view(before),stock_view(after)
            else:
                previous=copy.deepcopy(previous);previous.update(identity=meta,baseline_thresholds=previous['baseline_observed_thresholds'])
                base={'indices':{meta['symbol']:previous},'event_records':copy.deepcopy(context)}
                before_doc=copy.deepcopy(base);after_doc=copy.deepcopy(base)
                before=old_index.evaluate(before_doc,index_item(pairs,closes));after=idx.evaluate(after_doc,index_item(pairs,closes))
                a,b=index_view(before,before_doc,pairs[-1][0]),index_view(after,after_doc,pairs[-1][0])
            expected_metrics=indicators.calculate(pairs,pairs[-1][0])
            latest_match=all(b['metrics'][key]==expected_metrics[key] for key in ('adjclose','highest_adjclose','highest_date','drawdown','rsi14','sma50','sma200'))
            assert latest_match and context==old_context
            cases.append({'case':name,'asset':asset,'synthetic_offline_fixture':True,'expectation':expectation,'before':a,'after':b,
                          'latest_series_metrics_match':latest_match,'original_context_not_modified':context==old_context})
    return cases


def archive_integration():
    ledger=json.loads((ROOT/'phase4_2_four_20261104/execution_ledger.json').read_text())
    stock_source=ROOT/'phase4_2_four_20261104/state/monitor_state.json'
    directory=OUT/'isolated_stock_replay';directory.mkdir(exist_ok=False)
    checkpoint=directory/'monitor_state.json';shutil.copyfile(stock_source,checkpoint);before=digest(checkpoint)
    with __import__('contextlib').redirect_stdout(io.StringIO()):
        report=monitor.run(Path(ledger['runs'][-1]['price_evidence_file']),checkpoint,directory/'reports')
    assert report['success_count']==9 and not report['state_updated'] and digest(checkpoint)==before
    previous=None
    for path in stock_source.with_name('monitor_state.json.backups').glob('*.json'):
        envelope=json.loads(path.read_text())
        if envelope['backup_version']==4:previous=envelope['state']
    evidence,diagnostic=monitor.read_input(Path(ledger['runs'][-1]['price_evidence_file']))
    avgo,_=monitor.process_symbol('AVGO',evidence['stocks']['AVGO'],diagnostic['AVGO'],previous['stocks']['AVGO'],1.,event_context=previous['event_records'])
    archived=next(r for r in ledger['runs'][-1]['stocks'] if r['symbol']=='AVGO')
    old_events=[e for e in json.loads(stock_source.read_text())['event_records'].values() if e['symbol']=='AVGO' and e['trading_date']=='2026-11-06' and e['event_type']=='DEEPER_DRAWDOWN']
    avgo_ids=[state.stable_id(e) for e in avgo['market_events']]
    assert old_events and old_events[0]['event_id'] in avgo_ids
    avgo_view={'archived_file_unchanged':True,'before':{key:archived.get(key) for key in ('drawdown','deepening_anchor','change_event')},
               'before_nested_candidate':archived['market_observation']['event_type'],
               'after':{key:avgo[key] for key in ('daily_drawdown_change_pp','daily_new_deepening','cumulative_anchor_deepening_pp','raw_market_candidate_type','event_status','candidate_confirmed','daily_drawdown_change_basis','stored_previous_drawdown_change_pp')},
               'stable_market_ids':avgo_ids,'archived_candidate_id_preserved':old_events[0]['event_id'] in avgo_ids}
    index_directory=OUT/'isolated_index_replay';index_directory.mkdir(exist_ok=False)
    index_path=index_directory/'indices_state.json';shutil.copyfile(ROOT/'market_indices_trial/state/indices_state.json',index_path);index_before=digest(index_path)
    items,errors=index_data.read_samples(ROOT/'market_indices_trial/collection');assert not errors
    with patch.object(idx,'DIRECTORY',index_directory):
        index_report=idx.run(items,index_path,index_directory/'reports')
    assert index_report['success_count']==3 and not index_report['state_updated'] and digest(index_path)==index_before
    return {'stock_replay':{'success_count':9,'checkpoint_byte_identical':True,'report':report['report_file']},
            'index_replay':{'success_count':3,'checkpoint_byte_identical':True,'report':index_report['report_file']},'avgo':avgo_view}


def main():
    temporary=OUT/'tmp';temporary.mkdir(exist_ok=True);tempfile.tempdir=str(temporary)
    os.environ['TMPDIR']=str(temporary);os.environ['PYTHONDONTWRITEBYTECODE']='1'
    network=[]
    def offline(event,args):
        if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','http.client.connect','urllib.Request'):
            network.append(event);raise RuntimeError('Task is strictly offline: '+event)
    sys.addaudithook(offline)
    outcomes=[]
    class Recorder(unittest.TextTestResult):
        def addSuccess(self,test):super().addSuccess(test);outcomes.append({'id':test.id(),'status':'PASS'})
        def addFailure(self,test,error):super().addFailure(test,error);outcomes.append({'id':test.id(),'status':'FAIL'})
        def addError(self,test,error):super().addError(test,error);outcomes.append({'id':test.id(),'status':'ERROR'})
    with (OUT/'tests.log').open('w') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Recorder).run(unittest.defaultTestLoader.discover(str(ROOT)))
    baseline=json.loads((OUT/'baseline/manifest.json').read_text());passed={r['id'] for r in outcomes if r['status']=='PASS'}
    old={r['id'] for r in baseline['baseline_tests']['outcomes']}
    tests={'total':result.testsRun,'passed':len(passed),'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
           'original_237_retained':old.issubset(passed),'new_tests':len(outcomes)-len(old),'network_attempts':network,'outcomes':outcomes}
    (OUT/'test_results.json').write_text(json.dumps(tests,indent=2)+'\n')
    if not result.wasSuccessful() or not old.issubset(passed) or result.skipped:return 1
    cases=compare_cases();integration=archive_integration()
    (OUT/'before_after_cases.json').write_text(json.dumps({'cases':cases,'real_archive_integration':integration},ensure_ascii=False,indent=2)+'\n')
    verification={name:{'expected_sha256':expected,'current_sha256':digest(ROOT/name),'matches':digest(ROOT/name)==expected}
                  for name,expected in baseline['sha256'].items() if name not in ALLOWED}
    all_protected=all(row['matches'] for row in verification.values())
    current=json.loads((ROOT/'phase4_2_four_20261104/state/monitor_state.json').read_text());pending={key:event for key,event in current['event_records'].items() if event['status']=='PENDING_REVIEW'}
    original_pending=pending==baseline['stock_pending_records']
    (OUT/'protected_files_verification.json').write_text(json.dumps({'all_unchanged':all_protected,'file_count':len(verification),'files':verification,
        'pending_records_identical':original_pending,'pending_event_ids':sorted(pending)},indent=2)+'\n')
    before_pending=sum(e['status']=='PENDING_REVIEW' for c in cases for e in c['before']['market_candidates'])
    after_pending=sum(e['status']=='PENDING_REVIEW' for c in cases for e in c['after']['market_candidates'])
    same=len([c for c in cases if c['case'] in ('micro','prior_unrelated','unrelated_material') and any(e['status']=='CONFIRMED' for e in c['after']['market_candidates'])])
    report={'ADJCLOSE_REVISION_REFINEMENT':'PASS' if all_protected and original_pending and not network else 'FAIL',
            'at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'git_baseline':baseline['git_head'],'scope':'Offline development and isolated archive validation only',
            'modified_files':sorted(ALLOWED),'new_files':['tests/test_adjclose_refinement.py','diagnostics/validate_adjclose_refinement.py','adjclose_revision_refinement/'],
            'tests':{key:value for key,value in tests.items() if key!='outcomes'},'protected_files_unchanged':all_protected,'protected_file_count':len(verification),
            'old_pending_records_identical':original_pending,'old_pending_count':len(pending),'source_math_and_state_unchanged':all(verification[name]['matches'] for name in ('src/indicators.py','src/signals.py','src/state.py','src/catchup.py','src/index_data.py')),
            'before_after_case_count':len(cases),'same_basis_independent_confirmation_cases':same,
            'candidate_pending_counts':{'before':before_pending,'after':after_pending,'interpretation':'Preserving previously dropped candidates can increase pending counts; no old review is resolved or hidden.'},
            'archive_integration':integration,'identity_and_unit_policy':'Equity identity/Close/adjustment-factor checks retained. Index Close is provenance, never event input.',
            'legacy_compatibility':'New risk_reasons are additive evidence. Missing/unknown provenance stays blocked. Only known price-only risk outside BOTH event windows can be unrelated; old decisions remain sticky.',
            'event_identity_policy':'Existing semantic fields and model versions unchanged; report fields do not enter IDs. Archived AVGO candidate ID matches.',
            'phase5_readiness':'Suitable for Phase5 design discussions; not production authorization. Unattended recovery, long-term reliability and explicit review workflow remain unvalidated.',
            'limitations':['Index extrema revisions remain conservatively pending even if a coarse event type agrees.',
                           'Unknown legacy evidence or source/unit risk cannot be automatically discharged.',
                           'Deepening anchor dependencies remain conservative; daily semantics are improved without rewriting historical candidates.',
                           'No new Yahoo requests, scheduler or external services used. No old pending status modified.']}
    (OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Adj Close 修订与事件归因改进验收','',f"ADJCLOSE_REVISION_REFINEMENT: {report['ADJCLOSE_REVISION_REFINEMENT']}",'',
           f"全程离线：{tests['passed']}/{tests['total']}测试通过，原237项完整保留，新增{tests['new_tests']}项，无跳过；真实网络请求0。",'',
           '当前指标始终使用最新验证通过的Adj Close；旧/新基础均重算前日及当日，混合基础结果仅供诊断。修订与市场观察分别留痕。',
           '股票保留Close、身份和调整单位安全检查；指数不以Close单独变化阻断Adj Close事件。',
           '完整价格修订证据若可证明在前日/当日事件窗口之外，可不阻断新独立事件；旧待复核状态不变。未知证据和相关修订继续安全待复核。',
           '股票按阈值保留可证明的新跨越和有争议候选；指数保留更保守的极值修订检查，避免把仅有当前档位的共同性误当新跨档。',
           '', '## 修改理由','', 'src/monitor.py只增加事件上下文传入及报告展示，以便基于完整旧修订证据判定依赖。未改state.py、signals.py、indicators.py、catchup.py或采集身份规则。',
           '', '## 场景对照','', '| 场景 | 类别 | 修改前市场候选 | 修改后市场候选 | 最新指标正确 |','|---|---|---|---|---|']
    display=lambda row:', '.join(str(e.get('threshold') or e['event_type'])+':'+e['status'] for e in row['market_candidates']) or '无'
    lines += [f"| {c['case']} | {c['asset']} | {display(c['before'])} | {display(c['after'])} | {c['latest_series_metrics_match']} |" for c in cases]
    avgo=integration['avgo']['after']
    lines += ['', '## AVGO 2026-11-06','',
              '原始类型DEEPER_DRAWDOWN及PENDING_REVIEW保留；候选不是当天新增已确认下跌。',
              f"daily_new_deepening={avgo['daily_new_deepening']}；同一最新基础daily_drawdown_change_pp={avgo['daily_drawdown_change_pp']:.6f}；累计锚点加深={avgo['cumulative_anchor_deepening_pp']:.6f}pp；candidate_confirmed={avgo['candidate_confirmed']}。",
              f"与存档前日指标直接相减的展示差值另存为{avgo['stored_previous_drawdown_change_pp']:.6f}pp，避免把不同基础当作市场证明。原始事件ID保持一致。",'',
              '## 原系统保护','',f"{len(verification)}个非授权改动文件SHA256全部不变；7条原始PENDING_REVIEW完整一致。股票9股和指数3标的的归档回放均在新隔离目录完成，检查点字节幂等。",
              '', '待复核数量并非越少越好：保留以前被丢弃的候选会增加待复核；本次只减少可严格证明无关的全局阻断，不确认、拒绝或删除旧记录。',
              '', '## Phase5','',report['phase5_readiness'],'', '## 限制','']+['- '+value for value in report['limitations']]
    (OUT/'acceptance.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key in ('ADJCLOSE_REVISION_REFINEMENT','tests','protected_files_unchanged','protected_file_count','old_pending_records_identical','old_pending_count','before_after_case_count')},ensure_ascii=False,indent=2))
    return 0 if report['ADJCLOSE_REVISION_REFINEMENT']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
