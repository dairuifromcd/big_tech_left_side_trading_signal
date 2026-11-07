"""No external requests: all faults use mocks or local subprocesses."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src import state, monitor, phase4
import test_yahoo_nine as collector
from test_yahoo_nine_offline import fake_network, payload_for


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root/"state.json"
        shutil.copyfile(phase4.FORMAL, self.path)
        self.formal_hash = phase4.file_hash(phase4.FORMAL)

    def tearDown(self):
        self.assertEqual(self.formal_hash, phase4.file_hash(phase4.FORMAL))

    def execute(self, input_path=None, mode="OFFLINE_REPLAY"):
        with patch("sys.stdout", new=io.StringIO()):
            return phase4.execute(input_path, self.path, self.root/"reports", mode)

    def live_mock(self, statuses=None, overrides=None):
        with fake_network(statuses, overrides) as (_, calls):
            report = self.execute(mode="LIVE_FETCH")
        return report, calls

    def test_mock_live_entire_pipeline_and_repeat(self):
        r, calls = self.live_mock()
        self.assertEqual(len(calls), 9)
        self.assertEqual(r["result"], "PASS_PROVISIONAL")
        self.assertTrue(r["state_updated"])
        self.assertTrue(r["backup_files"])
        again = self.execute(Path(r["input_file"]))
        self.assertFalse(again["state_updated"])
        self.assertEqual(again["new_observation_events"], [])

    def test_429_halts_and_preserves_failed_and_skipped_stocks(self):
        old = state.load(self.path)
        r, calls = self.live_mock({"GOOGL":429})
        self.assertEqual(len(calls), 3)
        self.assertEqual(r["result"], "RATE_LIMITED")
        self.assertEqual(r["collection_results"][2]["retry_after"], "120")
        new = state.load(self.path)
        for symbol in state.SYMBOLS[2:]:
            self.assertEqual(old["stocks"][symbol], new["stocks"][symbol])

    def test_401_403_not_retried(self):
        r, calls = self.live_mock({"NVDA":401,"AAPL":403})
        self.assertEqual(len(calls), 2)
        self.assertFalse(r["state_updated"])
        self.assertEqual([s["error_category"] for s in r["collection_results"][:2]], ["HTTP_UNAUTHORIZED","HTTP_FORBIDDEN"])

    def test_dns_tls_timeout_preserve_all_state(self):
        for exc, category in [(socket.gaierror(-2,"injected"),"DNS_ERROR"), (ssl.SSLCertVerificationError(1,"injected"),"TLS_ERROR"), (TimeoutError("injected"),"TIMEOUT")]:
            with self.subTest(category=category), fake_network():
                if category == "DNS_ERROR":
                    target = patch.object(collector.socket,"getaddrinfo",side_effect=exc)
                else:
                    target = patch.object(collector.http.client,"HTTPSConnection",side_effect=exc)
                with target:
                    r = phase4.execute(state_path=self.path,output_dir=self.root/category,mode="LIVE_FETCH")
                self.assertFalse(r["state_updated"])
                self.assertTrue(all(s["error_category"] == category for s in r["collection_results"]))

    def test_invalid_json_partial_stock_preserved(self):
        before = state.load(self.path)["stocks"]["NVDA"]
        r, _ = self.live_mock(overrides={"NVDA":b"{broken"})
        self.assertEqual(r["result"], "PARTIAL_SUCCESS")
        self.assertEqual(before, state.load(self.path)["stocks"]["NVDA"])

    def test_missing_adjclose_partial_failure(self):
        payload = payload_for("NVDA")
        del payload["chart"]["result"][0]["indicators"]["adjclose"]
        before = state.load(self.path)["stocks"]["NVDA"]
        r,_ = self.live_mock(overrides={"NVDA":json.dumps(payload).encode()})
        self.assertEqual(r["collection_results"][0]["error_category"], "MISSING_ADJCLOSE")
        self.assertEqual(before,state.load(self.path)["stocks"]["NVDA"])

    def test_stale_capture_rejected_before_commit(self):
        before = phase4.file_hash(self.path)
        with state.lock(self.path), patch("sys.stdout",new=io.StringIO()):
            r = monitor._run_unlocked(state_path=self.path,output_dir=self.root,expected_target="2026-10-30")
        self.assertEqual(r["failure_count"],9)
        self.assertEqual(before,phase4.file_hash(self.path))

    def test_corrupt_state_clear_report_no_reset(self):
        self.path.write_text("BROKEN")
        r=self.execute()
        self.assertEqual(r["result"],"STATE_ERROR")
        self.assertFalse(r["state_updated"])
        self.assertEqual(self.path.read_text(),"BROKEN")

    def test_commit_interruption_old_state_intact(self):
        old=phase4.file_hash(self.path)
        original=os.replace
        def interrupted(src,dst):
            if Path(dst)==self.path:
                raise OSError("injected before atomic state replacement")
            return original(src,dst)
        with patch.object(state.os,"replace",side_effect=interrupted):
            r,_=self.live_mock()
        self.assertEqual(r["result"],"STATE_ERROR")
        self.assertFalse(r["state_updated"])
        self.assertEqual(old,phase4.file_hash(self.path))
        state.load(self.path)
        self.assertTrue(r["backup_files"])

    def test_directory_sync_failure_complete_new_state(self):
        original=state.sync_directory
        count=[0]
        def failure(path):
            # Parent sync after replacement can fail with new state already visible.
            if Path(path)==self.path.parent:
                count[0]+=1
                if count[0]==2:
                    raise OSError("injected after replacement")
            return original(path)
        with patch.object(state,"sync_directory",side_effect=failure):
            r,_=self.live_mock()
        self.assertEqual(r["result"],"STATE_ERROR")
        state.load(self.path)
        self.assertTrue(r["state_updated"])

    def test_explicit_backup_recovery_and_hash_validation(self):
        r,_=self.live_mock()
        backup=Path(r["backup_files"][-1])
        baseline=state.load(self.path)
        self.path.write_text("injected damaged state")
        result=state.recover(self.path,backup)
        self.assertTrue(result["recovered"])
        self.assertEqual(state.load(self.path)["stocks"],state.load(phase4.FORMAL)["stocks"])
        self.assertTrue(list(self.root.glob("*.damaged_*")))
        bad=json.loads(backup.read_text());bad["state_hash"]="wrong"
        broken=self.root/"bad_backup.json";broken.write_text(json.dumps(bad))
        with self.assertRaises(state.StateError):state.recover(self.path,broken)

    def test_backup_limit(self):
        for _ in range(6):
            with state.lock(self.path):state.save(self.path,state.load(self.path))
        self.assertEqual(len(list(self.path.with_name(self.path.name+".backups").glob("*.json"))),3)

    def test_competing_process_lock(self):
        code="from src import state; import sys\ntry:\n with state.lock(sys.argv[1]): print('ACQUIRED')\nexcept state.StateError:\n print('BLOCKED');sys.exit(73)"
        with state.lock(self.path):
            proc=subprocess.run([sys.executable,"-c",code,str(self.path)],capture_output=True,text=True,timeout=5)
            self.assertEqual(proc.returncode,73)
            self.assertIn("BLOCKED",proc.stdout)
            with state.lock(self.root/"different/state.json"):pass
        proc=subprocess.run([sys.executable,"-c",code,str(self.path)],capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,0)

    def test_abnormal_process_exit_releases_lock(self):
        code="from src import state; import sys,time\nwith state.lock(sys.argv[1]):\n print('READY',flush=True)\n time.sleep(30)"
        child=subprocess.Popen([sys.executable,"-c",code,str(self.path)],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),"READY")
            child.terminate();child.wait(timeout=5)
            with state.lock(self.path):pass
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stdout.close()

    def test_phase4_refuses_formal_state(self):
        with self.assertRaises(state.StateError):
            phase4.execute(state_path=phase4.FORMAL,output_dir=self.root)

    def test_report_failure_preserves_committed_event_ledger(self):
        original=collector.atomic_json
        def broken(path,value):
            if Path(path).name.startswith("monitor_indicators_"):
                raise OSError("injected report failure after commit")
            return original(path,value)
        with patch.object(collector,"atomic_json",side_effect=broken):
            r,_=self.live_mock()
        self.assertEqual(r["result"],"STATE_ERROR")
        saved=state.load(self.path)
        self.assertTrue(saved["event_records"])
        again=self.execute(Path(r["input_file"]))
        self.assertFalse(again["state_updated"])
        self.assertEqual(again["new_observation_events"],[])

    def test_replay_five_sessions_no_future_prices(self):
        with patch("sys.stdout",new=io.StringIO()):
            r=phase4.replay(output_dir=self.root/"replay")
        self.assertEqual(len(r["days"]),5)
        for day in r["days"]:
            path=self.root/"replay"/day["target"]/"prices.json"
            source=json.loads(path.read_text())
            self.assertTrue(all(row["trading_date"]<=day["target"] for s in source["stocks"].values() for row in s["rows"]))
            report=json.loads(Path(day["report"]).read_text())
            self.assertTrue(all(s["trading_date"]==day["target"] for s in report["stocks"]))
            self.assertTrue(day["idempotent"])
            self.assertTrue(all(s["window_samples"]==(len(source["stocks"][s["symbol"]]["rows"]) if s["symbol"]=="SPCX" else 252) for s in report["stocks"]))


if __name__=="__main__":unittest.main()
