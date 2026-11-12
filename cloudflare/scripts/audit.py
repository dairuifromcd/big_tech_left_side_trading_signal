"""Offline baseline, immutable-file verification and Python regression runner."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'phase5_1_cloudflare_free'
OUT.mkdir(exist_ok=True)

def hashes():
    ignored = {'.git', '.venv', '__pycache__', 'cloudflare', 'phase5_1_cloudflare_free'}
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ROOT.rglob('*')) if p.is_file() and not ignored.intersection(p.relative_to(ROOT).parts)}

def pending():
    doc = json.loads((ROOT/'phase4_2_four_20261104/state/monitor_state.json').read_text())
    return {k:v for k,v in doc['event_records'].items() if v['status']=='PENDING_REVIEW'}

if sys.argv[1] == 'capture':
    path = OUT/'baseline.json'
    if path.exists():
        raise SystemExit('Baseline already exists; refusing replacement')
    path.write_text(json.dumps({'sha256':hashes(), 'pending':pending()}, indent=2)+'\n')
elif sys.argv[1] == 'verify':
    base=json.loads((OUT/'baseline.json').read_text()); current=hashes()
    changes=[k for k,v in base['sha256'].items() if current.get(k)!=v]
    result={'all_unchanged':not changes,'file_count':len(base['sha256']), 'changed_or_missing':changes,
            'added_outside_poc':sorted(set(current)-set(base['sha256'])),
            'pending_records_identical':base['pending']==pending(),'pending_count':len(pending()),
            'pending_event_ids':sorted(pending())}
    (OUT/'protected_files_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));sys.exit(bool(changes) or not result['pending_records_identical'])
elif sys.argv[1] == 'test':
    sys.path.insert(0,str(ROOT))
    attempts=[]
    def offline(event,args):
        if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','http.client.connect','urllib.Request'):
            attempts.append(event);raise RuntimeError('OFFLINE_ONLY: '+event)
    sys.addaudithook(offline)
    with (OUT/'python_tests.log').open('w') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT)))
    report={'total':result.testsRun,'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'network_attempts':attempts}
    (OUT/'python_tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    sys.exit(not result.wasSuccessful() or bool(result.skipped) or bool(attempts))
