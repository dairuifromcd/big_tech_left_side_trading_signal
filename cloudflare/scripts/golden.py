"""Generate input/output fixtures from unmodified Python; never fetch or rewrite archives."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src import observations as obs, state, monitor, index_data, indicators
from tests.test_adjclose_refinement import scenario, seed, identity, DATES
from diagnostics.revision_scenarios import _snapshot
import market_calendar as cal
import test_yahoo_nine as phase2

OUT=ROOT/'cloudflare/fixtures';OUT.mkdir(exist_ok=True)
cases=[]
def add(name,symbol,pairs,closes,meta,previous,context=None,policy='EQUITY'):
    args=dict(symbol=symbol,pairs=pairs,closes=closes,identity=meta,previous=previous,context=context or {},policy=policy,
              normalized_price_fingerprint=state.fingerprint({d:float(p) for d,p in pairs}))
    try:
        model=obs.evaluate(symbol,pairs,closes,meta,previous,event_context=context,identity_policy=policy)
        ids=[]
        for e in model['market_events']:
            if policy=='INDEX':
                semantic={'category':'Market Indices','symbol':symbol,'trading_date':e['trading_date'],'event_type':e['event_type'],'threshold':e['threshold'],'event_model_version':'indices-revision-market-v2','rules_version':indicators.RULES_VERSION}
                ids.append(state.fingerprint(semantic))
            else:ids.append(state.stable_id(e))
        expected={'model':model,'event_ids':ids}
    except ValueError as e:expected={'error':str(e).split(':')[0]}
    cases.append({'name':name,'input':args,'expected':expected})

for asset in ('stock','index'):
    for name in ('unchanged','micro','material','high_same_tier','revision_only','mixed_material','disagreement','one_basis_only','unrelated_material','near_boundary','close_only','prior_unrelated','prior_related','prior_unknown','prior_source_risk'):
        pairs,closes,meta,prev,context=scenario(name,asset)
        add(asset+'/'+name,meta['symbol'],pairs,closes,meta,prev,context,'INDEX' if asset=='index' else 'EQUITY')

for name,last,next_price in [('baseline',85,85),('normal',85,84.9),('multi',99,69),('deeper',85,83),('recovery',75,85),('reentry',85,79),('boundary10',99,90),('boundary20',99,80),('boundary30',99,70)]:
    pairs,prev=seed(last=last);meta=identity('stock');new=pairs+[(DATES[490],next_price)]
    if name=='reentry':prev['threshold_state']['confirmed']=[20]
    add(name,'NVDA',new,dict(new),meta,None if name=='baseline' else prev)

pairs,closes,meta,prev,_=scenario('unchanged');event=obs.evaluate('NVDA',pairs,closes,meta,prev)['market_events'][0]
for status in ('PENDING_REVIEW','REJECTED'):
    add('existing_'+status,'NVDA',pairs,closes,meta,prev,{state.stable_id(event):{**event,'status':status}})
model=obs.evaluate('NVDA',pairs,closes,meta,prev)
updated={**model,'history_prices':dict(pairs),'history_closes':closes,'identity_snapshot':meta}
add('repeat','NVDA',pairs,closes,meta,updated)
add('missing_session_observation','NVDA',pairs+[(DATES[491],78)],{**closes,DATES[491]:78},meta,prev)
bad_meta={**meta,'currency':'EUR'}
add('identity_changed','NVDA',pairs,closes,bad_meta,prev)
for n in (1,14,15,49,50,199,200,251,252):
    short=[(d,100.) for d in DATES[:n]]
    # Pure calculator allows short only for SPCX; source validator separately enforces IPO.
    add('indicator_samples_'+str(n),'SPCX',short,dict(short),{**meta,'symbol':'SPCX'},None)
prices=[(d,120. if i==0 else 100.) for i,d in enumerate(DATES[238:490])]
base=obs.evaluate('NVDA',prices,dict(prices),meta,None)
old={**base,'history_prices':dict(prices),'history_closes':dict(prices),'identity_snapshot':meta}
new=prices+[(DATES[490],101.)];add('natural_high_expiry','NVDA',new,dict(new),meta,old)
prices,old=seed(last=90.000001);new=list(prices);new[300]=(new[300][0],100.00000762939453);new.append((DATES[490],79.))
add('per_level_mixed','NVDA',new,{**dict(prices),DATES[490]:79.},meta,old)

ledger=json.loads((ROOT/'phase4_2_four_20261104/execution_ledger.json').read_text())
evidence,diagnostic=monitor.read_input(Path(ledger['runs'][-1]['price_evidence_file']))
previous=next(json.loads(p.read_text())['state'] for p in (ROOT/'phase4_2_four_20261104/state/monitor_state.json.backups').glob('*.json') if json.loads(p.read_text())['backup_version']==4)
samples=[];validation=[]
for symbol in state.SYMBOLS:
    complete,target,checked,excluded=monitor.validated_prices(symbol,evidence['stocks'][symbol],diagnostic[symbol]);pairs=[(r['trading_date'],r['adjclose']) for r in complete];closes={r['trading_date']:r['close'] for r in complete}
    meta={k:diagnostic[symbol]['identity'].get(k) for k in ('symbol','longName','instrumentType','exchangeName','fullExchangeName','currency','exchangeTimezoneName')}
    add('archive/'+symbol,symbol,pairs,closes,meta,previous['stocks'][symbol],previous['event_records'])
    add('archive_baseline/'+symbol,symbol,pairs,closes,meta,None)
    sample={'symbol':symbol,'pairs':pairs,'closes':closes,'identity':meta,'target':target,'as_of_utc':evidence['stocks'][symbol]['as_of_utc'],'excluded_incomplete_dates':[],'data_quality':'PASS_PROVISIONAL' if symbol=='SPCX' else 'PASS'};samples.append(sample)
    rows=evidence['stocks'][symbol]['rows'];raw={'chart':{'error':None,'result':[{'meta':diagnostic[symbol]['identity'],'timestamp':[r['timestamp'] for r in rows],'indicators':{'adjclose':[{'adjclose':[r['adjclose'] for r in rows]}],'quote':[{'close':[r['close'] for r in rows]}]}}]}}
    validation.append({'name':'valid/'+symbol,'symbol':symbol,'raw':raw,'asof':sample['as_of_utc'],'pass':True,'target':target,'pairs':pairs})

items,errors=index_data.read_samples(ROOT/'market_indices_trial/collection');assert not errors
for symbol,item in items.items():
    samples.append({**item,'excluded_incomplete_dates':item['excluded_incomplete_dates']})
    add('archive_baseline/'+symbol,symbol,item['pairs'],item['closes'],item['identity'],None,policy='INDEX')
    raw=json.loads((ROOT/'market_indices_trial/collection'/f'{symbol[1:]}.json').read_text())
    validation.append({'name':'valid/'+symbol,'symbol':symbol,'raw':raw,'asof':item['as_of_utc'],'pass':True,'target':item['target'],'pairs':item['pairs']})

for source in [validation[0],validation[-1]]:
    for kind in ('identity','missing_adj','duplicate','missing_day','zero','null','short','bad_stamp','out_of_range','stale'):
        case=copy.deepcopy(source);case['name']=source['symbol']+'/'+kind;case['pass']=False;r=case['raw']['chart']['result'][0]
        if kind=='identity':r['meta']['currency']='EUR'
        elif kind=='missing_adj':del r['indicators']['adjclose']
        elif kind=='duplicate':r['timestamp'][10]=r['timestamp'][9]
        elif kind=='missing_day':
            for arr in (r['timestamp'],r['indicators']['adjclose'][0]['adjclose'],r['indicators']['quote'][0]['close']):del arr[10]
        elif kind in ('zero','null'):r['indicators']['adjclose'][0]['adjclose'][10]=0 if kind=='zero' else None
        elif kind=='short':
            r['timestamp']=r['timestamp'][-20:];r['indicators']['adjclose'][0]['adjclose']=r['indicators']['adjclose'][0]['adjclose'][-20:];r['indicators']['quote'][0]['close']=r['indicators']['quote'][0]['close'][-20:]
        elif kind=='bad_stamp':r['timestamp'][10]+=22*3600
        elif kind=='out_of_range':r['timestamp'][10]=0
        elif kind=='stale':case['asof']='2026-11-11T00:00:00+00:00'
        if source['symbol'] in state.SYMBOLS:
            checked=phase2.new_row(source['symbol'],1);phase2.analyze_payload(checked,case['raw'],dt.datetime.fromisoformat(case['asof']));assert not checked['data_quality_pass'],case['name']
        else:
            try:index_data.validate(source['symbol'],case['raw'],dt.datetime.fromisoformat(case['asof']))
            except ValueError:pass
            else:raise AssertionError(case['name'])
        validation.append(case)

(OUT/'golden.json').write_text(json.dumps(cases,allow_nan=False,separators=(',',':'))+'\n')
(OUT/'samples.json').write_text(json.dumps(samples,allow_nan=False,separators=(',',':'))+'\n')
(OUT/'validation.json').write_text(json.dumps(validation,allow_nan=False,separators=(',',':'))+'\n')
(OUT/'legacy-pending.json').write_text(json.dumps({k:v for k,v in json.loads((ROOT/'phase4_2_four_20261104/state/monitor_state.json').read_text())['event_records'].items() if v['status']=='PENDING_REVIEW'},indent=2)+'\n')
print(json.dumps({'golden':len(cases),'validation':len(validation),'samples':len(samples)}))
