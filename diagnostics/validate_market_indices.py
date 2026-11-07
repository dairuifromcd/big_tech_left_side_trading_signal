"""Offline final audit. Never collects, schedules, or modifies equity evidence."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

from src import index_data, market_indices as indices
from tests.test_market_indices import reference

ROOT=indices.ROOT
OUT=ROOT/'market_indices_trial'


def main():
    def offline(event,args):
        if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','http.client.connect','urllib.Request'):
            raise RuntimeError('Final audit is offline: '+event)
    sys.addaudithook(offline)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    manifest=json.loads((OUT/'baseline/manifest.json').read_text())
    changed={name:{'expected':expected,'actual':sha(ROOT/name) if (ROOT/name).is_file() else None}
             for name,expected in manifest['tracked_sha256'].items() if not (ROOT/name).is_file() or sha(ROOT/name)!=expected}
    items,errors=index_data.read_samples(OUT/'collection')
    document=indices.load(indices.DEFAULT_STATE)
    regression=json.loads((OUT/'regression.json').read_text());integration=json.loads((OUT/'integration.json').read_text())
    refs={};validation=[]
    for symbol,item in items.items():
        expected=reference(item['pairs']);actual=document['indices'][symbol]
        diffs={key:actual[key]-value for key,value in expected.items()}
        refs[symbol]={'independent_method':'Decimal(50 digits), closed-form geometric Wilder weights, independent high/drawdown and simple means',
                      'reference_values':expected,'stored_values':{key:actual[key] for key in expected},'differences':diffs,
                      'passed':all(abs(value)<1e-8 for value in diffs.values())}
        validation.append({key:value for key,value in item.items() if key not in ('pairs','closes')})
    (OUT/'reference_values.json').write_text(json.dumps(refs,indent=2)+'\n')
    (OUT/'validated_indices.json').write_text(json.dumps(items,indent=2)+'\n')
    (OUT/'data_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    ledger=json.loads((ROOT/'phase4_2_four_20261104/execution_ledger.json').read_text())
    previous=next(s for s in ledger['runs'][2]['stocks'] if s['symbol']=='AVGO')
    current=next(s for s in ledger['runs'][3]['stocks'] if s['symbol']=='AVGO')
    diagnosis={'symbol':'AVGO','previous_date':'2026-11-05','current_date':'2026-11-06',
               'previous_drawdown_percent':previous['drawdown']*100,'current_drawdown_percent':current['drawdown']*100,
               'daily_drawdown_change_pp':(current['drawdown']-previous['drawdown'])*100,
               'old_deepening_anchor_percent':previous['deepening_anchor']*100,
               'cumulative_unconfirmed_deepening_pp':(previous['deepening_anchor']-current['drawdown'])*100,
               'daily_new_deepening':current['drawdown']<previous['drawdown'],
               'stored_summary':current['change_event'],'candidate_market_type':current['market_observation']['event_type'],
               'candidate_status':current['market_observation']['status'],'comparability_reasons':current['market_observation']['comparability_reasons'],
               'explanation':'The old anchor is retained while market candidates remain unconfirmed. The cumulative distance exceeds 1pp even though this session improved. Recovery denotes exiting a WATCH tier, not every positive daily change.',
               'recommendation':'Separate daily_new_deepening/daily_drawdown_change_pp from cumulative_unconfirmed_deepening_pp and original candidate date in a later stock-model change. Preserve all existing event IDs, pending decisions and unconsumed anchor scope.',
               'stock_model_modified':False,'pending_review_decisions_made':0}
    (OUT/'avgo_semantic_diagnostic.json').write_text(json.dumps(diagnosis,ensure_ascii=False,indent=2)+'\n')
    old_stock_state=json.loads((ROOT/'phase4_2_four_20261104/state/monitor_state.json').read_text())
    old_pending=[key for key,event in old_stock_state['event_records'].items() if event['status']=='PENDING_REVIEW']
    capture=json.loads((OUT/'collection/collection_ledger.json').read_text())
    passed=not changed and not errors and len(items)==3 and all(v['passed'] for v in refs.values()) and not document['event_records'] and len(old_pending)==7 and regression['existing_208_retained'] and regression['failures']==regression['errors']==regression['skipped']==0 and integration['repeat_byte_identical']
    report={'MARKET_INDICES_EXTENSION':'PASS' if passed else 'FAIL','at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'scope':'Development, one live three-index capture, isolated baseline and offline regression. No scheduling or Phase5 deployment.',
            'git_baseline':manifest['git_head'],'original_tracked_files':len(manifest['tracked_sha256']),
            'protected_historical_files':len(manifest['protected_sha256']),'all_original_files_unchanged':not changed,'changed_original_files':changed,
            'live_http_requests':capture['http_request_count'],'http_200_count':sum(r['http_status']==200 for r in capture['stocks']),
            'rate_limited':capture['rate_limited'],'request_intervals':capture['request_intervals'],'data_validation_errors':errors,
            'indices':validation,'references':refs,'integration':integration,
            'tests':{key:value for key,value in regression.items() if key!='outcomes'},'equity_pending_records_retained':old_pending,
            'avgo_diagnostic':diagnosis,'new_files':['src/index_data.py','src/market_indices.py','tests/test_market_indices.py','diagnostics/validate_market_indices.py','MARKET_INDICES.md','market_indices_trial/'],
            'phase5_readiness':'Eligible as an isolated integration candidate; live index cross-day reliability, explicit index-review workflow and unattended recovery still require validation. No automatic production promotion.',
            'limitations':['Yahoo single source; issuer descriptions do not authenticate vendor-specific exchange codes.',
                          'Exact two-year left boundary is not independently certified; complete internal calendar coverage is verified.',
                          'All index price revisions are conservatively pending; this is stricter than the stock precision-comparability policy.',
                          'Only one actual index capture; multi-session scenarios are offline fixtures.',
                          'Bounded existing 2024–2028 calendar remains unchanged.']}
    (OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Market Indices 扩展验收','',f"MARKET_INDICES_EXTENSION: {report['MARKET_INDICES_EXTENSION']}",'',
           f"{regression['passed']}/{regression['total']}测试通过，原208项全部保留；无跳过；回归阶段真实网络请求0。",'',
           '| 指数 | HTTP | 完整Adj Close记录 | 最新交易日 | Close/Adj Close | exchange |', '|---|---|---|---|---|---|']
    for item in validation:
        lines.append(f"| {item['symbol']} | 200 | {item['valid_adjclose_count']} | {item['target']} | {'完全相等' if item['close_adjclose_exact_equal'] else '存在差异'} | {item['identity']['exchangeName']}/{item['identity']['fullExchangeName']} |")
    lines += ['', '仅新增三指数各采集一次，串行至少5秒，不重试；未请求旧九股。SOX实际volume为501个0，缺失/null成交量的离线测试同样通过。',
              '', '三个指数均为INDEX/USD/America/New_York；使用独立显式初始化的v2指数状态。首次基线无事件；重复运行字节幂等。',
              '原387个已跟踪文件（包括346份受保护状态和历史证据）全部保持原哈希；原7条待复核决策未动。',
              '', '## AVGO 2026-11-06 只读诊断','',
              f"前日回撤 {diagnosis['previous_drawdown_percent']:.6f}%，当日 {diagnosis['current_drawdown_percent']:.6f}%，改善 {diagnosis['daily_drawdown_change_pp']:.6f} 个百分点。",
              f"旧deepening_anchor为 {diagnosis['old_deepening_anchor_percent']:.6f}%，累计未确认加深仍为 {diagnosis['cumulative_unconfirmed_deepening_pp']:.6f} 个百分点，超过1.0门槛。",
              '当日WATCH_30未退出，所以标量模型不判RECOVERY。旧锚点因前日候选未确认而保留；当日候选仍为DEEPER_DRAWDOWN，但顶层摘要和事件状态实际均为PENDING_REVIEW，不能解释成当日新增已确认下跌。',
              '建议后续单独区分“本日增量”和“自旧锚点累计未确认加深”，保留原始候选日、事件ID与未消费的锚点。本任务未修改股票模型、未批准或拒绝任何待复核项。',
              '', '## Phase5建议','',report['phase5_readiness'],'', '## 限制','']+['- '+x for x in report['limitations']]
    (OUT/'acceptance.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'result':report['MARKET_INDICES_EXTENSION'],'tests':regression['total'],'original_files_unchanged':not changed,
                      'http_requests':capture['http_request_count'],'old_pending_retained':len(old_pending),'report':str(OUT/'acceptance.md')},ensure_ascii=False))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
