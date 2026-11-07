"""Offline safety regression; fixed fixtures, no production evidence writes."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import market_calendar as calendar
from src import monitor, observations, state
from src import catchup, phase4
from diagnostics.revision_scenarios import _base_pairs, _snapshot
from tests.test_phase4_1 import process, FORMAL, digest


class SafetyCases(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'state.json'
        self.formal_hash=digest(FORMAL)
        for name in ('socket.getaddrinfo','socket.create_connection','http.client.HTTPSConnection.connect'):
            p=patch(name,side_effect=AssertionError('Offline only'));p.start();self.addCleanup(p.stop)

    def tearDown(self):self.assertEqual(self.formal_hash,digest(FORMAL))

    def document(self):
        shutil.copyfile(FORMAL,self.path);state.migrate_path(self.path)
        return state.load(self.path)

    def revision(self,risk=False,version=1,status=None):
        return {'symbol':'NVDA','trading_date':'2026-10-29','event_type':'REVISION_OBSERVATION',
                'threshold':None,'status':status or ('PENDING_REVIEW' if risk else 'CONFIRMED'),
                'evidence':{'revision_observation':{'requires_review':risk,'version':version},'snapshot_fingerprint':str(version)}}

    def test_u1_same_revision_id_escalates_risk(self):
        doc=self.document();event_id,_=state.register_event(doc,self.revision())
        same,_=state.register_event(doc,self.revision(True,2))
        self.assertEqual(event_id,same)
        event=doc['event_records'][event_id]
        self.assertEqual(event['status'],'PENDING_REVIEW','P0: worse revision remained CONFIRMED')
        self.assertEqual(len(event['evidence_versions']),2)
        self.assertEqual(event['audit_trail'][-1]['action'],'RISK_ESCALATION')

    def test_m1_missing_state_fails_closed(self):
        self.path.write_text('{}');self.path.unlink()
        with self.assertRaisesRegex(state.StateError,'MISSING_EXISTING_STATE'):
            state.load(self.path)
        self.assertFalse(self.path.exists())

    def test_c1_gap_identified_and_old_checkpoint_retained(self):
        pairs,day=_base_pairs();_,previous=process(pairs)
        after=calendar.sessions_between(dt.date.fromisoformat(day)+dt.timedelta(days=1),dt.date(2026,12,31))[0].isoformat()
        stock,diag=_snapshot(pairs+[(day,81.),(after,79.)])
        with self.assertRaisesRegex(ValueError,'CATCHUP_REQUIRED'):
            monitor.process_symbol('NVDA',stock,diag,previous,1.)

    def test_u2_identical_evidence_is_byte_idempotent(self):
        doc=self.document();event=self.revision();first,_=state.register_event(doc,event)
        state.save(self.path,doc);before=self.path.read_bytes()
        loaded=state.load(self.path);old=copy.deepcopy(loaded)
        same,new=state.register_event(loaded,event)
        self.assertEqual(first,same);self.assertFalse(new);self.assertEqual(old,loaded)
        self.assertEqual(before,self.path.read_bytes())

    def test_u3_pending_is_sticky_until_explicit_review(self):
        doc=self.document();eid,_=state.register_event(doc,self.revision(True,1))
        state.register_event(doc,self.revision(False,2));self.assertEqual(doc['event_records'][eid]['status'],'PENDING_REVIEW')
        state.save(self.path,doc)
        state.review_event(self.path,eid,'CONFIRM','Fixed local review evidence accepted')
        self.assertEqual(state.load(self.path)['event_records'][eid]['status'],'CONFIRMED')
        self.assertNotIn(eid,state.load(self.path)['stocks']['NVDA']['revision_review_event_ids'])

    def test_u4_rejected_new_evidence_blocks_without_mutation(self):
        doc=self.document();event=self.revision(False,1,status='REJECTED')
        eid,_=state.register_event(doc,event);before=copy.deepcopy(doc)
        state.register_event(doc,event);self.assertEqual(doc,before)
        with self.assertRaisesRegex(state.StateError,'REOPEN_REQUIRED'):
            state.register_event(doc,self.revision(True,2))
        self.assertEqual(doc,before);self.assertEqual(doc['event_records'][eid]['status'],'REJECTED')

    def test_u5_escalated_refs_and_next_session_risk_are_consistent(self):
        doc=self.document();eid,_=state.register_event(doc,self.revision(False,1))
        state.register_event(doc,self.revision(True,2));state.validate_v2(doc)
        self.assertIn(eid,doc['stocks']['NVDA']['revision_review_event_ids'])
        self.assertIn(eid,doc['stocks']['NVDA']['threshold_state']['pending_event_ids'])
        state.save(self.path,doc);self.assertEqual(state.load(self.path)['event_records'][eid]['status'],'PENDING_REVIEW')
        pairs,day=_base_pairs();_,old=process(pairs);old['revision_review_event_ids']=[eid]
        observation,_=process(pairs+[(day,79.)],old)
        self.assertIn('UNRESOLVED_PRIOR_REVISION_REVIEW',observation['market_observation']['comparability_reasons'])
        self.assertNotIn(20,observation['confirmed_thresholds'])

    def test_u_market_confirmation_is_flagged_not_silently_revoked(self):
        doc=self.document();market,_=state.register_event(doc,{'symbol':'NVDA','trading_date':'2026-10-29',
            'event_type':'THRESHOLD_CROSSING','threshold':20,'status':'CONFIRMED','evidence':{'fixed':'market'}})
        stock=doc['stocks']['NVDA'];stock['confirmed_thresholds']=[20];stock['triggered_thresholds']=[20];stock['threshold_state']['confirmed']=[20]
        eid,_=state.register_event(doc,self.revision());state.register_event(doc,self.revision(True,2))
        self.assertEqual(doc['event_records'][market]['status'],'CONFIRMED')
        self.assertIn(eid,doc['event_records'][market]['dependency_review_event_ids'])
        state.validate_v2(doc)

    def test_m2_missing_primary_with_backup_lists_verified_recovery(self):
        doc=self.document();state.save(self.path,doc);before=copy.deepcopy(state.load(self.path))
        backups=state.list_backups(self.path);self.assertTrue(backups);self.assertTrue(all(b['valid'] for b in backups))
        self.path.unlink()
        with self.assertRaisesRegex(state.StateError,'MISSING_EXISTING_STATE'):state.load(self.path)
        with self.assertRaisesRegex(state.StateError,'INITIALIZATION_REFUSED'):state.initialize(self.path)
        result=state.recover(self.path,backups[-1]['path']);self.assertTrue(result['recovered'])
        state.load(self.path);self.assertTrue(list(self.path.with_name(self.path.name+'.recovery_audit').glob('*.json')))

    def test_m3_explicit_init_first_baseline_then_normal_repeat(self):
        state.initialize(self.path)
        with patch('sys.stdout',new=io.StringIO()):
            first=monitor.run(state_path=self.path,output_dir=self.root)
            before=self.path.read_bytes();again=monitor.run(state_path=self.path,output_dir=self.root)
        self.assertTrue(all(s['change_event']=='FIRST_BASELINE' for s in first['stocks']))
        self.assertFalse(first['new_observation_events']);self.assertFalse(again['state_updated'])
        self.assertEqual(before,self.path.read_bytes())

    def test_m4_existing_or_previously_initialized_state_cannot_reinitialize(self):
        state.initialize(self.path);before=self.path.read_bytes()
        with self.assertRaisesRegex(state.StateError,'INITIALIZATION_REFUSED'):state.initialize(self.path)
        self.assertEqual(before,self.path.read_bytes());self.path.unlink()
        with self.assertRaisesRegex(state.StateError,'INITIALIZATION_REFUSED'):state.initialize(self.path)

    def test_m5_wrong_path_all_normal_entrypoints_fail_without_baseline(self):
        wrong=self.root/'typo'/'state.json'
        with self.assertRaisesRegex(state.StateError,'MISSING_EXISTING_STATE'):
            monitor.run(state_path=wrong,output_dir=self.root/'out')
        self.assertFalse(wrong.parent.exists())
        with patch('sys.stdout',new=io.StringIO()):r=phase4.execute(state_path=wrong,output_dir=self.root/'reports')
        self.assertEqual(r['result'],'STATE_ERROR');self.assertFalse(wrong.exists())
        child=subprocess.run([sys.executable,'-m','src.review','--state',str(wrong),'--list-pending'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(child.returncode,0);self.assertIn('MISSING_EXISTING_STATE',child.stderr)

    def test_m5_explicit_init_refuses_unrelated_existing_directory(self):
        (self.root/'unrelated.txt').write_text('Existing non-state work must be protected')
        with self.assertRaisesRegex(state.StateError,'fresh isolated directory'):
            state.initialize(self.path)
        self.assertFalse(self.path.exists());self.assertFalse(self.path.with_name(self.path.name+'.initialized.json').exists())

    def test_m5_formal_path_is_rejected_before_optional_fetch(self):
        with patch('sys.argv',['monitor','--state',str(FORMAL),'--fetch']),patch.object(monitor.phase2,'run') as fetch,patch('sys.stderr',new=io.StringIO()):
            with self.assertRaises(SystemExit) as exit:
                monitor.main()
        self.assertNotEqual(exit.exception.code,0);fetch.assert_not_called()

    def catchup_fixture(self):
        pairs,missing=_base_pairs();_,old=process(pairs)
        following=calendar.sessions_between(dt.date.fromisoformat(missing)+dt.timedelta(days=1),dt.date(2026,12,31))[0].isoformat()
        doc,_=state.migrate({'schema_version':1,'rules_version':old['rules_version'],'stocks':{'NVDA':old}})
        state.initialize(self.path,doc)
        return pairs,missing,following

    def run_snapshot(self,pairs,mode='ARCHIVED_CATCHUP'):
        stock,diag=_snapshot(pairs)
        # Fixed synthetic capture taken after that session, no future rows.
        diag['request_end_utc']=stock['as_of_utc']
        with patch.object(monitor,'read_input',return_value=({'stocks':{'NVDA':stock}},{'NVDA':diag})),patch('sys.stdout',new=io.StringIO()):
            return monitor.run(state_path=self.path,output_dir=self.root,mode=mode)

    def test_c2_fixed_consecutive_archives_preserve_order_and_ids(self):
        pairs,missing,following=self.catchup_fixture()
        one=self.run_snapshot(pairs+[(missing,79.)]);self.assertEqual(one['success_count'],1)
        before=self.path.read_bytes();again=self.run_snapshot(pairs+[(missing,79.)]);self.assertFalse(again['state_updated']);self.assertEqual(before,self.path.read_bytes())
        two=self.run_snapshot(pairs+[(missing,79.),(following,78.)]);self.assertEqual(two['success_count'],1)
        self.assertEqual(state.load(self.path)['stocks']['NVDA']['trading_date'],following)
        self.assertTrue(all(e.get('origin_mode')=='ARCHIVED_CATCHUP' for e in state.load(self.path)['event_records'].values()))

    def test_c3_later_snapshot_only_yields_blocked_reconstructed_plan(self):
        pairs,missing,following=self.catchup_fixture();stock,diag=_snapshot(pairs+[(missing,81.),(following,79.)])
        before=self.path.read_bytes()
        with patch.object(monitor,'read_input',return_value=({'stocks':{'NVDA':stock}},{'NVDA':diag})):
            plan=catchup.plan(Path('in-memory'),self.path)
        row=plan['stocks'][0];self.assertEqual(row['mode'],'RECONSTRUCTED_CATCHUP');self.assertEqual(row['status'],'PENDING_REVIEW')
        self.assertEqual(row['missing_sessions'],[missing]);self.assertEqual(plan['catchup_safety'],'BLOCKED')
        self.assertEqual(before,self.path.read_bytes())

    def test_c4_incomplete_missing_day_blocks_progress(self):
        pairs,missing,following=self.catchup_fixture();stock,diag=_snapshot(pairs+[(missing,81.),(following,79.)])
        stock['rows'][-2]['adjclose']=None;before=self.path.read_bytes()
        with patch.object(monitor,'read_input',return_value=({'stocks':{'NVDA':stock}},{'NVDA':diag})),patch('sys.stdout',new=io.StringIO()):
            result=monitor.run(state_path=self.path,output_dir=self.root)
        self.assertEqual(result['success_count'],0);self.assertEqual(before,self.path.read_bytes())

    def test_c5_interruption_resumes_from_last_complete_checkpoint(self):
        pairs,missing,following=self.catchup_fixture()
        self.run_snapshot(pairs+[(missing,79.)]);before=self.path.read_bytes();old=state.load(self.path)
        original=state.os.replace
        def interrupted(src,dst):
            if Path(dst)==self.path:raise OSError('Injected catchup commit interruption')
            return original(src,dst)
        with patch.object(state.os,'replace',side_effect=interrupted):
            with self.assertRaises(OSError):self.run_snapshot(pairs+[(missing,79.),(following,78.)])
        self.assertEqual(before,self.path.read_bytes());self.assertEqual(state.load(self.path)['event_records'],old['event_records'])
        self.run_snapshot(pairs+[(missing,79.),(following,78.)]);done=self.path.read_bytes()
        self.run_snapshot(pairs+[(missing,79.),(following,78.)]);self.assertEqual(done,self.path.read_bytes())

    def test_c3_backdated_reconstruction_cannot_claim_original_capture(self):
        pairs,missing,following=self.catchup_fixture()
        stock,diag=_snapshot(pairs+[(missing,81.)])
        later,_=_snapshot(pairs+[(missing,81.),(following,79.)])
        diag['request_end_utc']=later['as_of_utc'];before=self.path.read_bytes()
        with patch.object(monitor,'read_input',return_value=({'stocks':{'NVDA':stock}},{'NVDA':diag})),patch('sys.stdout',new=io.StringIO()):
            r=monitor.run(state_path=self.path,output_dir=self.root,mode='ARCHIVED_CATCHUP')
        self.assertEqual(r['success_count'],0);self.assertEqual(before,self.path.read_bytes())
        self.assertIn('RECONSTRUCTED_CATCHUP',r['stocks'][0]['error_message'])

    def test_u1_full_pipeline_escalates_same_id_and_repeat_is_unchanged(self):
        pairs,_=_base_pairs();_,previous=process(pairs)
        doc,_=state.migrate({'schema_version':1,'rules_version':previous['rules_version'],'stocks':{'NVDA':previous}})
        state.initialize(self.path,doc)
        def run_prices(values):
            stock,diag=_snapshot(values)
            for row in stock['rows']:row['close']=dict(pairs)[row['trading_date']]
            with patch.object(monitor,'read_input',return_value=({'stocks':{'NVDA':stock}},{'NVDA':diag})),patch('sys.stdout',new=io.StringIO()):
                return monitor.run(state_path=self.path,output_dir=self.root)
        minor=list(pairs);minor[10]=(pairs[10][0],90.0001)
        run_prices(minor);old=state.load(self.path);eid=next(i for i,e in old['event_records'].items() if e['event_type']=='REVISION_OBSERVATION')
        self.assertEqual(old['event_records'][eid]['status'],'CONFIRMED')
        major=list(minor);major[1]=(pairs[1][0],110.)
        run_prices(major);new=state.load(self.path)
        self.assertEqual(new['event_records'][eid]['status'],'PENDING_REVIEW');self.assertEqual(len(new['event_records'][eid]['evidence_versions']),2)
        self.assertIn(eid,new['stocks']['NVDA']['revision_review_event_ids']);state.validate_v2(new)
        before=self.path.read_bytes();again=run_prices(major);self.assertFalse(again['state_updated']);self.assertEqual(before,self.path.read_bytes())


if __name__=='__main__':unittest.main()
