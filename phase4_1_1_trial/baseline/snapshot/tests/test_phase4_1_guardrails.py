"""Additional transactional and small-scale proof guardrails; all offline."""
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src import monitor, state
from diagnostics.revision_scenarios import _base_pairs, _snapshot
import datetime as dt
import market_calendar as calendar
from tests.test_phase4_1 import process, digest, FORMAL


class Guardrails(unittest.TestCase):
    def test_unresolved_high_review_survives_next_session(self):
        pairs,day = _base_pairs();_,previous=process(pairs)
        revised=list(pairs);revised[1]=(revised[1][0],110.);revised.append((day,81.))
        _,pending=process(revised,previous)
        self.assertTrue(pending["revision_observation"]["requires_review"])
        next_day=calendar.sessions_between(dt.date.fromisoformat(day)+dt.timedelta(days=1),dt.date(2026,12,31))[0].isoformat()
        observation,_=process(revised+[(next_day,70.)],pending)
        self.assertIn("UNRESOLVED_PRIOR_REVISION_REVIEW",observation["market_observation"]["comparability_reasons"])
        self.assertTrue(observation["market_events"])
        self.assertTrue(all(e["status"]=="PENDING_REVIEW" for e in observation["market_events"]))
        self.assertNotIn(30,observation["confirmed_thresholds"])

    def test_tiny_adjustment_factor_changes_require_review(self):
        pairs, day = _base_pairs()
        closes = {d:p*1e6 for d,p in pairs}
        _, previous = process(pairs, closes=closes)
        newer = pairs+[(day,79.)]
        closes[day] = 79./(1e-6+5e-9)
        observed,_ = process(newer, previous, closes=closes)
        self.assertFalse(observed["market_observation"]["can_confirm"])
        self.assertIn("CURRENT_ADJUSTMENT_FACTOR_INCOMPARABLE",observed["market_observation"]["comparability_reasons"])
        self.assertEqual(observed["market_events"][0]["status"],"PENDING_REVIEW")

    def test_partial_event_registration_cannot_leak_into_failed_stock(self):
        pairs,day = _base_pairs()
        _,previous = process(pairs)
        document,_ = state.migrate({"schema_version":1,"rules_version":previous["rules_version"],"stocks":{"NVDA":previous}})
        revised=list(pairs);revised[10]=(pairs[10][0],90.0001);revised.append((day,79.))
        stock,diag=_snapshot(revised)
        for row in stock["rows"]:
            if row["trading_date"] in dict(pairs):row["close"]=dict(pairs)[row["trading_date"]]
        original=state.register_event
        calls=[]
        def interrupted(doc,event):
            calls.append(event["event_type"])
            if event["event_type"]=="REVISION_OBSERVATION":raise state.StateError("injected second-event failure")
            return original(doc,event)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"state.json";state.save(p,document);before=p.read_bytes()
            with patch.object(monitor,"read_input",return_value=({"stocks":{"NVDA":stock}},{"NVDA":diag})),patch.object(state,"register_event",side_effect=interrupted),patch("sys.stdout",new=io.StringIO()):
                result=monitor.run(state_path=p,output_dir=directory)
            self.assertIn("THRESHOLD_CROSSING",calls)
            self.assertEqual(result["failure_count"],9)
            self.assertEqual(before,p.read_bytes())
            self.assertFalse(result["new_observation_events"])

    def test_all_failed_run_keeps_even_v1_checkpoint_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"state.json";shutil.copyfile(FORMAL,p);before=p.read_bytes()
            with patch("sys.stdout",new=io.StringIO()):
                result=monitor._run_unlocked(state_path=p,output_dir=directory,expected_target="2026-10-30")
            self.assertEqual(result["failure_count"],9)
            self.assertFalse(result["state_updated"])
            self.assertEqual(before,p.read_bytes())

    def test_comparison_evidence_tamper_fails_closed(self):
        pairs,_ = _base_pairs();_,stock=process(pairs)
        doc,_ = state.migrate({"schema_version":1,"rules_version":stock["rules_version"],"stocks":{"NVDA":stock}})
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"state.json";state.save(p,doc)
            changed=json.loads(p.read_text());changed["stocks"]["NVDA"]["history_closes"][pairs[0][0]]+=1
            p.write_text(json.dumps(changed))
            with self.assertRaisesRegex(state.StateError,"fingerprint"):
                state.load(p)

    def test_formal_state_cannot_be_implicitly_migrated(self):
        before=digest(FORMAL)
        with self.assertRaisesRegex(state.StateError,"ISOLATION_ERROR"):
            monitor._run_unlocked()
        self.assertEqual(before,digest(FORMAL))


if __name__ == "__main__":unittest.main()
