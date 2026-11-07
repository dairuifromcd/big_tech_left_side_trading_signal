"""Independent index quality, reference mathematics and state isolation tests."""
import copy
import datetime as dt
from decimal import Decimal, localcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import market_calendar as calendar
from src import index_data as data, market_indices as module, indicators, state

ROOT=Path(__file__).resolve().parents[1]


def reference(pairs):
    with localcontext() as context:
        context.prec=50
        values=[Decimal(str(p)) for _,p in pairs];changes=[b-a for a,b in zip(values,values[1:])]
        gains=sum(max(x,Decimal(0)) for x in changes[:14])/14
        losses=sum(max(-x,Decimal(0)) for x in changes[:14])/14
        # Independent closed-form geometric weights, not the production recurrence.
        tail=changes[14:];decay=Decimal(13)/14;count=len(tail)
        gains=gains*decay**count+sum(max(x,Decimal(0))/14*decay**(count-i-1) for i,x in enumerate(tail))
        losses=losses*decay**count+sum(max(-x,Decimal(0))/14*decay**(count-i-1) for i,x in enumerate(tail))
        rsi=Decimal(50) if gains==losses==0 else Decimal(100) if losses==0 else Decimal(100)-Decimal(100)/(1+gains/losses)
        high=max(values[-252:])
        return {'highest_adjclose':float(high),'drawdown':float(values[-1]/high-1),'rsi14':float(rsi),
                'sma50':float(sum(values[-50:])/50),'sma200':float(sum(values[-200:])/200)}


def raw(symbol):
    return json.loads((ROOT/'market_indices_trial/collection'/f'{symbol[1:]}.json').read_text())


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items,errors=data.read_samples(ROOT/'market_indices_trial/collection')
        assert not errors,errors

    def test_three_real_indices_and_independent_decimal_references(self):
        for symbol,item in self.items.items():
            with self.subTest(symbol=symbol):
                self.assertGreaterEqual(item['valid_adjclose_count'],252)
                for key,value in reference(item['pairs']).items():
                    self.assertAlmostEqual(indicators.calculate(item['pairs'],item['target'])[key],value,places=8)

    def test_instrument_identity_is_index(self):
        p=raw('^NDX');p['chart']['result'][0]['meta']['instrumentType']='EQUITY'
        with self.assertRaisesRegex(ValueError,'IDENTITY_MISMATCH'):
            data.validate('^NDX',p,dt.datetime.fromisoformat(self.items['^NDX']['as_of_utc']))

    def test_each_identity_field_is_checked(self):
        for key,value in (('symbol','QQQ'),('currency','AUD'),('exchangeName','NMS'),('exchangeTimezoneName','UTC'),('longName','Wrong index')):
            p=raw('^NDX');p['chart']['result'][0]['meta'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'IDENTITY_MISMATCH'):
                data.validate('^NDX',p,dt.datetime.fromisoformat(self.items['^NDX']['as_of_utc']))

    def test_missing_adjclose_never_uses_close(self):
        p=raw('^GSPC');del p['chart']['result'][0]['indicators']['adjclose']
        with self.assertRaisesRegex(ValueError,'MISSING_ADJCLOSE'):
            data.validate('^GSPC',p,dt.datetime.fromisoformat(self.items['^GSPC']['as_of_utc']))

    def test_sox_missing_volume_does_not_invalidate_prices(self):
        p=raw('^SOX');p['chart']['result'][0]['indicators']['quote'][0].pop('volume',None)
        item=data.validate('^SOX',p,dt.datetime.fromisoformat(self.items['^SOX']['as_of_utc']))
        self.assertEqual(item['pairs'],self.items['^SOX']['pairs'])

    def test_null_volume_does_not_invalidate_prices(self):
        p=raw('^SOX');p['chart']['result'][0]['indicators']['quote'][0]['volume']=[None]*len(p['chart']['result'][0]['timestamp'])
        self.assertEqual(data.validate('^SOX',p,dt.datetime.fromisoformat(self.items['^SOX']['as_of_utc']))['data_quality'],'PASS')

    def test_unfinished_null_bar_is_excluded(self):
        p=raw('^GSPC');r=p['chart']['result'][0];day=dt.date(2026,11,9);start,end=calendar.session_bounds(day)
        r['timestamp'].append(int(start.timestamp()));r['indicators']['quote'][0]['close'].append(None);r['indicators']['adjclose'][0]['adjclose'].append(None)
        item=data.validate('^GSPC',p,start+dt.timedelta(hours=1))
        self.assertEqual(item['target'],'2026-11-06');self.assertEqual(item['excluded_incomplete_dates'],['2026-11-09'])

    def test_duplicate_dates_rejected(self):
        p=raw('^GSPC');p['chart']['result'][0]['timestamp'][-1]=p['chart']['result'][0]['timestamp'][-2]
        with self.assertRaisesRegex(ValueError,'DATA_QUALITY_ERROR'):
            data.validate('^GSPC',p,dt.datetime.fromisoformat(self.items['^GSPC']['as_of_utc']))

    def test_invalid_complete_prices_rejected(self):
        for price in (None,0,-1,float('nan'),float('inf')):
            p=raw('^GSPC');p['chart']['result'][0]['indicators']['adjclose'][0]['adjclose'][-1]=price
            with self.subTest(price=price),self.assertRaisesRegex(ValueError,'DATA_QUALITY_ERROR'):
                data.validate('^GSPC',p,dt.datetime.fromisoformat(self.items['^GSPC']['as_of_utc']))

    def test_stale_data_rejected(self):
        with self.assertRaisesRegex(ValueError,'STALE_DATA'):
            data.validate('^GSPC',raw('^GSPC'),calendar.session_bounds(dt.date(2026,11,9))[1]+dt.timedelta(minutes=1))

    def test_inconsistent_lengths_rejected(self):
        p=raw('^GSPC');p['chart']['result'][0]['indicators']['adjclose'][0]['adjclose'].pop()
        with self.assertRaisesRegex(ValueError,'length mismatch'):
            data.validate('^GSPC',p,dt.datetime.fromisoformat(self.items['^GSPC']['as_of_utc']))

    def test_malformed_payload_fails_cleanly(self):
        for payload in (None,{'chart':None},{'chart':{'result':[None]}}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                data.validate('^GSPC',payload,dt.datetime.fromisoformat(self.items['^GSPC']['as_of_utc']))

    def test_tampered_raw_capture_is_isolated(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'market_indices_trial/tests_tmp') as tmp:
            directory=Path(tmp);ledger=json.loads((ROOT/'market_indices_trial/collection/collection_ledger.json').read_text())
            for row in ledger['stocks']:
                name=Path(row['raw_file']).name
                (directory/name).write_bytes((ROOT/'market_indices_trial/collection'/name).read_bytes())
            (directory/'GSPC.json').write_text('{}');(directory/'collection_ledger.json').write_text(json.dumps(ledger))
            items,errors=data.read_samples(directory)
            self.assertEqual(set(items),{'^NDX','^SOX'});self.assertIn('HASH_MISMATCH',errors['^GSPC'])


class StateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items,errors=data.read_samples(ROOT/'market_indices_trial/collection')
        assert not errors,errors

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'market_indices_trial/tests_tmp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'indices_state.json'
        context=patch.object(module,'DIRECTORY',self.root);context.start();self.addCleanup(context.stop)
        module.initialize(self.path)
        self.dates=[d for d,_ in self.items['^GSPC']['pairs']]

    def item(self,prices,symbol='^GSPC'):
        item=copy.deepcopy(self.items[symbol]);n=len(prices);item.update(pairs=list(zip(self.dates[:n],prices)),closes=dict(zip(self.dates[:n],prices)),target=self.dates[n-1])
        item['as_of_utc']=(calendar.session_bounds(dt.date.fromisoformat(item['target']))[1]+dt.timedelta(minutes=1)).isoformat()
        return item

    def process(self,item):
        return module.run({item['symbol']:item},self.path,self.root/'reports')

    def test_initial_baseline_has_no_false_threshold(self):
        self.process(self.item([100]*259+[65]))
        value=module.load(self.path);self.assertFalse(value['event_records']);self.assertEqual(value['indices']['^GSPC']['watch_tier'],'WATCH_30')

    def test_threshold_recovery_and_reentry(self):
        prices=[100]*260;self.process(self.item(prices))
        events=[]
        for price in (89,79,95,85):
            prices.append(price);events.append(self.process(self.item(prices))['indices'][0]['change_event'])
        self.assertEqual(events,['NEW_THRESHOLD','NEW_THRESHOLD','RECOVERY','REENTRY'])
        self.assertEqual(module.load(self.path)['indices']['^GSPC']['confirmed_thresholds'],[10,20])

    def test_significant_deepening(self):
        prices=[100]*259+[85];self.process(self.item(prices));prices.append(83)
        self.assertEqual(self.process(self.item(prices))['indices'][0]['change_event'],'DEEPER_DRAWDOWN')

    def test_identical_replay_preserves_state_bytes_and_events(self):
        prices=[100]*260;self.process(self.item(prices));prices.append(85);item=self.item(prices);self.process(item)
        before=self.path.read_bytes();result=self.process(item)
        self.assertFalse(result['state_updated']);self.assertEqual(self.path.read_bytes(),before)

    def test_revision_only_cannot_create_threshold(self):
        prices=[100]*259+[95];self.process(self.item(prices));prices[150]=200;prices.append(95)
        self.process(self.item(prices));value=module.load(self.path)
        self.assertEqual(value['indices']['^GSPC']['confirmed_thresholds'],[])
        self.assertEqual({e['event_type'] for e in value['event_records'].values()},{'REVISION_OBSERVATION'})

    def test_market_and_revision_candidate_stays_pending(self):
        prices=[100]*260;self.process(self.item(prices));prices[100]+=0.000001;prices.append(85)
        self.process(self.item(prices));value=module.load(self.path)
        self.assertEqual(value['indices']['^GSPC']['confirmed_thresholds'],[])
        self.assertTrue(all(e['status']=='PENDING_REVIEW' for e in value['event_records'].values()))
        self.assertEqual(value['indices']['^GSPC']['deepening_anchor'],0)

    def test_missed_session_preserves_previous_state(self):
        prices=[100]*260;self.process(self.item(prices));before=self.path.read_bytes();prices.extend([90,80])
        result=self.process(self.item(prices));self.assertIn('CATCHUP_REQUIRED',result['indices'][0]['error']);self.assertEqual(self.path.read_bytes(),before)

    def test_index_failure_does_not_prevent_other_index_commit(self):
        bad=self.item([100]*260);bad['identity']['currency']='EUR';good=self.item([100]*260,'^NDX')
        module.run({'^GSPC':bad,'^NDX':good},self.path,self.root/'reports');self.assertEqual(set(module.load(self.path)['indices']),{'^NDX'})

    def test_cannot_initialize_over_existing_or_lost_state(self):
        with self.assertRaisesRegex(ValueError,'INITIALIZATION_REFUSED'):module.initialize(self.path)
        self.path.unlink()
        with self.assertRaisesRegex(ValueError,'MISSING_EXISTING_INDEX_STATE'):module.load(self.path)
        with self.assertRaisesRegex(ValueError,'INITIALIZATION_REFUSED'):module.initialize(self.path)

    def test_index_state_rejected_by_equity_loader(self):
        with self.assertRaises(state.StateError):state.load(self.path)

    def test_equity_state_path_cannot_be_used(self):
        with self.assertRaisesRegex(ValueError,'INDEX_STATE_ISOLATION_ERROR'):module.initialize(ROOT/'state/monitor_state.json')

    def test_corrupt_index_state_is_not_reset(self):
        self.path.write_text('{bad json')
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):module.load(self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_revision_risk_escalates_and_pending_stays_pending(self):
        doc=module.load(self.path);args=(doc,'^GSPC','2026-11-06','REVISION_OBSERVATION',None)
        key=module.register(*args,'CONFIRMED',{'risk':False});module.register(*args,'PENDING_REVIEW',{'risk':True});module.register(*args,'CONFIRMED',{'risk':'new lower evidence'})
        self.assertEqual(doc['event_records'][key]['status'],'PENDING_REVIEW');self.assertEqual(len(doc['event_records'][key]['evidence_versions']),3)


class CollectorTests(unittest.TestCase):
    def test_429_stops_after_one_request(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'market_indices_trial/tests_tmp') as tmp:
            response=type('Response',(),{'status':429,'getheader':lambda self,k:'60' if k=='Retry-After' else None,'read':lambda self:b'limit'})()
            with patch.object(data.socket,'getaddrinfo',return_value=[object()]),patch.object(data.http.client,'HTTPSConnection') as cls:
                cls.return_value.getresponse.return_value=response
                result=data.collect(Path(tmp));self.assertEqual(result['http_request_count'],1);self.assertTrue(result['rate_limited'])
                self.assertEqual(cls.return_value.request.call_count,1)
            with self.assertRaisesRegex(ValueError,'COLLECTION_ALREADY_CLAIMED'):data.collect(Path(tmp))

    def test_auth_denial_stops_without_retry(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'market_indices_trial/tests_tmp') as tmp:
            response=type('Response',(),{'status':403,'getheader':lambda self,k:None,'read':lambda self:b'denied'})()
            with patch.object(data.socket,'getaddrinfo',return_value=[object()]),patch.object(data.http.client,'HTTPSConnection') as cls:
                cls.return_value.getresponse.return_value=response
                self.assertEqual(data.collect(Path(tmp))['http_request_count'],1)


class AVGOReadOnlyTests(unittest.TestCase):
    def test_improving_day_has_cumulative_unconfirmed_anchor_candidate(self):
        ledger=json.loads((ROOT/'phase4_2_four_20261104/execution_ledger.json').read_text())
        previous=next(r for r in ledger['runs'][2]['stocks'] if r['symbol']=='AVGO')
        current=next(r for r in ledger['runs'][3]['stocks'] if r['symbol']=='AVGO')
        self.assertGreater(current['drawdown'],previous['drawdown'])
        self.assertEqual(current['deepening_anchor'],previous['deepening_anchor'])
        self.assertGreater((previous['deepening_anchor']-current['drawdown'])*100,1)
        self.assertEqual(current['change_event'],'PENDING_REVIEW')
        self.assertEqual(current['market_observation']['event_type'],'DEEPER_DRAWDOWN')
        self.assertFalse(current['market_observation']['can_confirm'])
