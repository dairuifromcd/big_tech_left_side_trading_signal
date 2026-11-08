"""Offline attribution proofs and archive preservation; no live requests."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import market_calendar as calendar
from src import indicators, observations as obs, monitor, market_indices as idx, index_data, state

ROOT=Path(__file__).resolve().parents[1]
DATES=[d.isoformat() for d in calendar.sessions_between(dt.date(2024,11,7),dt.date(2026,11,6))]


def identity(asset):
    if asset=='stock':return {'symbol':'NVDA','longName':'NVIDIA Corporation','instrumentType':'EQUITY','exchangeName':'NMS','fullExchangeName':'NasdaqGS','currency':'USD','exchangeTimezoneName':'America/New_York'}
    return {'symbol':'^GSPC','longName':'S&P 500','shortName':'S&P 500','instrumentType':'INDEX','exchangeName':'SNP','fullExchangeName':'SNP','currency':'USD','exchangeTimezoneName':'America/New_York'}


def seed(asset='stock',last=85.):
    pairs=[(day,100. if i==300 else last if i==489 else 90.) for i,day in enumerate(DATES[:490])]
    meta=identity(asset);symbol=meta['symbol']
    model=obs.evaluate(symbol,pairs,dict(pairs),meta,None,identity_policy='INDEX' if asset=='index' else 'EQUITY')
    old={**model,'history_prices':dict(pairs),'history_closes':dict(pairs),'identity_snapshot':meta}
    return pairs,old


def scenario(name,asset='stock'):
    pairs,old=seed(asset)
    newer=list(pairs);closes=dict(pairs);context={};next_price=79.
    if name=='unchanged':pass
    elif name=='micro':newer[470]=(newer[470][0],90.0001)
    elif name=='material':newer[300]=(newer[300][0],110.)
    elif name=='high_same_tier':newer[300]=(newer[300][0],100.5);next_price=85.
    elif name=='revision_only':newer[300]=(newer[300][0],110.);next_price=85.
    elif name=='mixed_material':newer[300]=(newer[300][0],110.);next_price=75.
    elif name=='disagreement':newer[300]=(newer[300][0],110.);next_price=81.
    elif name=='one_basis_only':newer[300]=(newer[300][0],110.);next_price=79.
    elif name=='unrelated_material':newer[10]=(newer[10][0],50.)
    elif name=='near_boundary':newer[470]=(newer[470][0],90.0001);next_price=79.999999
    elif name=='close_only':closes[pairs[100][0]]=91.
    elif name in ('prior_unrelated','prior_related','prior_unknown','prior_source_risk'):
        date=pairs[10 if name=='prior_unrelated' else 300][0]
        revision={'raw_differences':[{'date':date,'previous':90.,'current':91.}],
                  'risk_reasons':['IDENTITY_PROVENANCE_MISSING_OR_CHANGED'] if name=='prior_source_risk' else ['ROLLING_EXTREMUM_REVISED']}
        if name=='prior_unknown':revision={}
        event={'symbol':identity(asset)['symbol'],'event_type':'REVISION_OBSERVATION','trading_date':old['trading_date'],
               'status':'PENDING_REVIEW','evidence_versions':[{'evidence':{'revision_observation':revision}}]}
        context={'old-risk':event};old['revision_review_event_ids']=['old-risk']
    else:raise ValueError(name)
    newer.append((DATES[490],next_price));closes[DATES[490]]=next_price
    return newer,closes,identity(asset),old,context


def observe(name,asset='stock',engine=obs):
    pairs,closes,meta,old,context=scenario(name,asset)
    return engine.evaluate(meta['symbol'],pairs,closes,meta,old,event_context=context,identity_policy='INDEX' if asset=='index' else 'EQUITY')


def index_item(pairs,closes=None):
    target=pairs[-1][0]
    return {'symbol':'^GSPC','identity':identity('index'),'pairs':pairs,'closes':closes or dict(pairs),'target':target,
            'as_of_utc':(calendar.session_bounds(dt.date.fromisoformat(target))[1]+dt.timedelta(minutes=1)).isoformat()}


class AttributionTests(unittest.TestCase):
    def test_01_unchanged_adjclose_confirms_real_crossing_on_both_bases(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('unchanged',asset);self.assertEqual(row['confirmed_thresholds'],[20]);self.assertFalse(row['revision_observation']['detected'])

    def test_02_irrelevant_micro_revision_retained_and_market_confirmed(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('micro',asset);self.assertEqual(row['confirmed_thresholds'],[20]);self.assertEqual(row['revision_observation']['count'],1)
                self.assertNotEqual(row['revision_observation']['impact_at_current_target']['deltas']['rsi14'],0)

    def test_03_material_related_revision_remains_pending(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('material',asset);self.assertFalse(row['confirmed_thresholds']);self.assertTrue(row['market_events']);self.assertTrue(all(e['status']=='PENDING_REVIEW' for e in row['market_events']))

    def test_04_revised_high_same_tier_recomputes_latest_high(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('high_same_tier',asset);self.assertEqual(row['highest_adjclose'],100.5);self.assertEqual(row['watch_tier'],'WATCH_10')
                self.assertTrue(row['revision_observation']['impact_at_current_target']['changed']['highest_adjclose'])

    def test_05_revision_changes_watch_but_not_confirmed_market(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('revision_only',asset);self.assertEqual(row['watch_tier'],'WATCH_20');self.assertAlmostEqual(row['drawdown'],85/110-1)
                self.assertFalse(row['market_events']);self.assertFalse(row['confirmed_thresholds'])

    def test_06_revision_does_not_turn_an_existing_tier_into_a_new_crossing(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('one_basis_only',asset);market=row['market_observation']
                self.assertIn(20,market['old_basis_new_crossings']);self.assertNotIn(20,market['latest_basis_new_crossings'])
                self.assertIn(20,market['pending_thresholds_this_run']);self.assertNotIn(20,row['confirmed_thresholds'])

    def test_07_micro_revision_and_market_trigger_are_separate(self):
        row=observe('micro');self.assertTrue(row['revision_observation']['detected']);self.assertEqual(row['market_events'][0]['event_type'],'THRESHOLD_CROSSING')
        self.assertTrue(row['market_events'][0]['evidence']['comparability_proven'])

    def test_08_material_mixed_case_preserves_candidates(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('mixed_material',asset);levels={e['threshold'] for e in row['market_events']}
                self.assertIn(20,levels);self.assertIn(30,levels);self.assertTrue(all(e['status']=='PENDING_REVIEW' for e in row['market_events']))

    def test_09_disagreement_never_discards_the_candidate(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('disagreement',asset);self.assertEqual({e['threshold'] for e in row['market_events']},{20})
                self.assertEqual(row['market_events'][0]['status'],'PENDING_REVIEW')

    def test_10_undisputed_level_can_be_confirmed_while_boundary_level_is_pending(self):
        pairs,old=seed(last=90.000001);new=list(pairs);new[300]=(new[300][0],100.00000762939453);new.append((DATES[490],79.))
        row=obs.evaluate('NVDA',new,{**dict(pairs),DATES[490]:79.},identity('stock'),old)
        statuses={e['threshold']:e['status'] for e in row['market_events']}
        self.assertEqual(statuses,{10:'PENDING_REVIEW',20:'CONFIRMED'});self.assertEqual(row['confirmed_thresholds'],[20])
        self.assertEqual(row['deepening_anchor'],old['deepening_anchor'])

    def test_11_old_unrelated_risk_does_not_globally_block_new_event(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('prior_unrelated',asset);self.assertEqual(row['confirmed_thresholds'],[20])
                self.assertEqual(row['market_observation']['revision_dependency_assessment'][0]['classification'],'PROVEN_OUTSIDE_EVENT_WINDOWS')

    def test_12_old_related_or_unknown_or_source_risk_still_blocks(self):
        for asset in ('stock','index'):
            for case in ('prior_related','prior_unknown','prior_source_risk'):
                with self.subTest(asset=asset,case=case):
                    row=observe(case,asset);self.assertFalse(row['confirmed_thresholds']);self.assertEqual(row['market_events'][0]['status'],'PENDING_REVIEW')

    def test_13_repeat_does_not_generate_a_new_market_event_or_id(self):
        pairs,closes,meta,old,context=scenario('micro');first=obs.evaluate(meta['symbol'],pairs,closes,meta,old)
        updated={**first,'history_prices':dict(pairs),'history_closes':closes,'identity_snapshot':meta}
        again=obs.evaluate(meta['symbol'],pairs,closes,meta,updated)
        self.assertFalse(again['market_events']);self.assertEqual(again['confirmed_thresholds'],first['confirmed_thresholds'])

    def test_14_avgo_archive_improves_daily_with_unconfirmed_cumulative_depth(self):
        ledger=json.loads((ROOT/'phase4_2_four_20261104/execution_ledger.json').read_text())
        previous=None
        for p in (ROOT/'phase4_2_four_20261104/state/monitor_state.json.backups').glob('*.json'):
            envelope=json.loads(p.read_text())
            if envelope['backup_version']==4:previous=envelope['state']
        self.assertIsNotNone(previous)
        evidence,diagnostic=monitor.read_input(Path(ledger['runs'][3]['price_evidence_file']))
        row,_=monitor.process_symbol('AVGO',evidence['stocks']['AVGO'],diagnostic['AVGO'],previous['stocks']['AVGO'],1.,event_context=previous['event_records'])
        self.assertFalse(row['daily_new_deepening']);self.assertAlmostEqual(row['daily_drawdown_change_pp'],0.4501,places=4)
        self.assertAlmostEqual(row['stored_previous_drawdown_change_pp'],0.4500577341)
        self.assertAlmostEqual(row['cumulative_anchor_deepening_pp'],5.9466431747);self.assertEqual(row['event_status'],'PENDING_REVIEW')
        self.assertFalse(row['candidate_confirmed']);self.assertEqual(row['raw_market_candidate_type'],'DEEPER_DRAWDOWN')

    def test_15_index_close_only_changes_do_not_block_but_equity_stays_strict(self):
        index=observe('close_only','index');stock=observe('close_only','stock')
        self.assertEqual(index['confirmed_thresholds'],[20]);self.assertFalse(stock['confirmed_thresholds'])
        self.assertIn('OVERLAP_CLOSE_CHANGED',stock['market_observation']['comparability_reasons'])

    def test_16_index_missing_adjclose_cannot_fallback_to_close(self):
        raw=json.loads((ROOT/'market_indices_trial/collection/GSPC.json').read_text());del raw['chart']['result'][0]['indicators']['adjclose']
        with self.assertRaisesRegex(ValueError,'MISSING_ADJCLOSE'):
            index_data.validate('^GSPC',raw,dt.datetime(2026,11,7,12,tzinfo=dt.timezone.utc))

    def test_17_index_and_equity_paths_and_event_ids_stay_distinct(self):
        with self.assertRaisesRegex(ValueError,'INDEX_STATE_ISOLATION_ERROR'):idx.allowed_path(ROOT/'state/monitor_state.json')
        event={'symbol':'NVDA','trading_date':DATES[490],'event_type':'THRESHOLD_CROSSING','threshold':20}
        self.assertEqual(state.stable_id(event),state.stable_id({**event,'daily_new_deepening':False,'event_status':'PENDING_REVIEW'}))

    def test_18_all_seven_original_pending_records_remain_byte_identical(self):
        baseline=json.loads((ROOT/'adjclose_revision_refinement/baseline/manifest.json').read_text())
        current=json.loads((ROOT/'phase4_2_four_20261104/state/monitor_state.json').read_text())
        self.assertEqual({k:v for k,v in current['event_records'].items() if v['status']=='PENDING_REVIEW'},baseline['stock_pending_records'])

    def test_19_all_archived_states_and_evidence_sha256_unchanged(self):
        baseline=json.loads((ROOT/'adjclose_revision_refinement/baseline/manifest.json').read_text())
        for name,digest in baseline['sha256'].items():
            if Path(name).parts[0] in ('state','reports','phase4_trial','phase4_1_trial','phase4_1_1_trial','phase4_2_trial','phase4_2_manual_20261103','phase4_2_four_20261104','market_indices_trial'):
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)

    def test_20_failed_index_does_not_pollute_other_index_state(self):
        self.root=Path(tempfile.mkdtemp());self.addCleanup(__import__('shutil').rmtree,self.root)
        path=self.root/'indices_state.json';items,_=index_data.read_samples(ROOT/'market_indices_trial/collection');bad=copy.deepcopy(items['^GSPC']);bad['identity']['currency']='EUR'
        with patch.object(idx,'DIRECTORY',self.root):
            idx.initialize(path);report=idx.run({'^GSPC':bad,'^NDX':items['^NDX']},path,self.root/'reports')
            self.assertEqual(set(idx.load(path)['indices']),{'^NDX'});self.assertEqual(report['success_count'],1)

    def test_21_near_boundary_micro_revision_remains_pending(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):self.assertEqual(observe('near_boundary',asset)['market_events'][0]['status'],'PENDING_REVIEW')

    def test_22_material_warmup_revision_has_metric_impacts_but_independent_event(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('unrelated_material',asset);self.assertEqual(row['confirmed_thresholds'],[20]);self.assertTrue(row['revision_observation']['requires_review'])
                self.assertEqual(row['revision_observation']['market_dependency'],'PROVEN_OUTSIDE_EVENT_WINDOWS')

    def test_23_existing_pending_market_id_never_promotes_or_consumes_anchor(self):
        pairs,closes,meta,old,_=scenario('unchanged');first=obs.evaluate('NVDA',pairs,closes,meta,old);event=first['market_events'][0]
        context={state.stable_id(event):{**event,'status':'PENDING_REVIEW'}}
        row=obs.evaluate('NVDA',pairs,closes,meta,old,event_context=context)
        self.assertFalse(row['confirmed_thresholds']);self.assertEqual(row['deepening_anchor'],old['deepening_anchor'])

    def test_24_rejected_market_decision_requires_explicit_reopening(self):
        pairs,closes,meta,old,_=scenario('unchanged');event=obs.evaluate('NVDA',pairs,closes,meta,old)['market_events'][0]
        with self.assertRaisesRegex(ValueError,'REOPEN_REQUIRED'):
            obs.evaluate('NVDA',pairs,closes,meta,old,event_context={state.stable_id(event):{**event,'status':'REJECTED'}})

    def test_25_rollover_of_old_high_is_not_a_revision(self):
        pairs,old=seed();prices=[(d,120. if i==0 else 100.) for i,(d,p) in enumerate(pairs[-252:])]
        base=obs.evaluate('NVDA',prices,dict(prices),identity('stock'),None)
        old={**base,'history_prices':dict(prices),'history_closes':dict(prices),'identity_snapshot':identity('stock')}
        newer=prices+[(DATES[490],101.)];row=obs.evaluate('NVDA',newer,dict(newer),identity('stock'),old)
        self.assertFalse(row['revision_observation']['detected']);self.assertTrue(row['market_observation']['window_high_expired_naturally'])

    def test_26_no_revision_old_pending_review_is_not_automatically_changed(self):
        pairs,closes,meta,old,context=scenario('prior_unrelated');before=copy.deepcopy(context)
        obs.evaluate(meta['symbol'],pairs,closes,meta,old,event_context=context)
        self.assertEqual(context,before)

    def test_27_real_index_adapter_confirms_non_extremum_micro_revision(self):
        pairs,old=seed('index');doc={'indices':{},'event_records':{}}
        idx.evaluate(doc,index_item(pairs));new,closes,_,_,_=scenario('micro','index')
        row=idx.evaluate(doc,index_item(new,closes))
        self.assertEqual(row['confirmed_thresholds'],[20]);self.assertTrue(row['comparability_proven'])
        self.assertEqual({e['event_type'] for e in doc['event_records'].values()},{'THRESHOLD_CROSSING','REVISION_OBSERVATION'})
        self.assertTrue(all(e['status']=='CONFIRMED' for e in doc['event_records'].values()))

    def test_28_real_index_adapter_keeps_disputed_candidates(self):
        pairs,_=seed('index');doc={'indices':{},'event_records':{}};idx.evaluate(doc,index_item(pairs))
        new,closes,_,_,_=scenario('mixed_material','index');idx.evaluate(doc,index_item(new,closes))
        self.assertEqual({e['threshold'] for e in doc['event_records'].values() if e['event_type']=='THRESHOLD_CROSSING'},{20,30})
        self.assertTrue(all(e['status']=='PENDING_REVIEW' for e in doc['event_records'].values()))

    def test_29_index_close_only_same_day_keeps_latest_close_provenance_without_events(self):
        root=Path(tempfile.mkdtemp());self.addCleanup(__import__('shutil').rmtree,root);path=root/'indices_state.json'
        pairs,_=seed('index');item=index_item(pairs)
        with patch.object(idx,'DIRECTORY',root):
            idx.initialize(path);idx.run({'^GSPC':item},path,root/'reports');before=idx.load(path)
            item['closes'][pairs[100][0]]=91.
            report=idx.run({'^GSPC':item},path,root/'reports');after=idx.load(path)
            self.assertTrue(report['state_updated']);self.assertEqual(after['indices']['^GSPC']['history_closes'][pairs[100][0]],91.)
            self.assertEqual(before['indices']['^GSPC']['drawdown'],after['indices']['^GSPC']['drawdown']);self.assertFalse(after['event_records'])
            payload=path.read_bytes();idx.run({'^GSPC':item},path,root/'reports');self.assertEqual(payload,path.read_bytes())

    def test_30_missing_sessions_fail_before_equity_state_advance(self):
        from diagnostics.revision_scenarios import _snapshot
        pairs,_=seed();stock,diag=_snapshot(pairs);_,previous=monitor.process_symbol('NVDA',stock,diag,None,1.)
        missing=pairs+[(DATES[490],84.),(DATES[491],79.)];stock,diag=_snapshot(missing)
        with self.assertRaises(monitor.CatchupRequired):monitor.process_symbol('NVDA',stock,diag,previous,1.)

    def test_31_no_current_raw_revision_still_compares_prior_risk_provenance(self):
        for case in ('prior_unrelated','prior_related'):
            row=observe(case)
            self.assertEqual(row['revision_observation']['count'],0)
            self.assertEqual(row['market_observation']['can_confirm'],case=='prior_unrelated')

    def test_32_current_and_previous_metrics_have_explicit_same_basis_views(self):
        row=observe('micro');basis=row['market_observation']['same_basis_comparison']
        self.assertEqual(basis['old_current']['trading_date'],basis['latest_current']['trading_date'])
        self.assertEqual(basis['old_previous']['trading_date'],basis['latest_previous']['trading_date'])
        self.assertAlmostEqual(row['latest_basis_daily_drawdown_change_pp'],(basis['latest_current']['drawdown']-basis['latest_previous']['drawdown'])*100)

    def test_33_revision_only_tier_change_is_not_daily_new_deepening(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                row=observe('revision_only',asset)
                self.assertFalse(row['daily_new_deepening']);self.assertEqual(row['daily_drawdown_change_pp'],0)
                self.assertLess(row['stored_previous_drawdown_change_pp'],0)

    def test_34_legacy_missing_review_refs_are_recovered_from_readonly_ledger(self):
        for asset in ('stock','index'):
            with self.subTest(asset=asset):
                pairs,closes,meta,old,context=scenario('prior_related',asset)
                old.pop('revision_review_event_ids')
                row=obs.evaluate(meta['symbol'],pairs,closes,meta,old,event_context=context,identity_policy='INDEX' if asset=='index' else 'EQUITY')
                self.assertFalse(row['confirmed_thresholds']);self.assertEqual(row['market_events'][0]['status'],'PENDING_REVIEW')


if __name__=='__main__':unittest.main()
