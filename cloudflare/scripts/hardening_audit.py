"""Phase 5.1A isolated regression and immutable baseline; no network or old outputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'phase5_1a_hardening'
OUT.mkdir(exist_ok=True)
ALLOWED = {'cloudflare/src/storage.ts', 'cloudflare/src/coordinator.ts', 'cloudflare/src/core.ts',
           'cloudflare/src/worker.ts', 'cloudflare/tests/parity.test.ts', 'cloudflare/tests/runtime.test.ts',
           'cloudflare/scripts/local.mjs'}

def hashes():
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names if name}

def pending():
    doc = json.loads((ROOT / 'phase4_2_four_20261104/state/monitor_state.json').read_text())
    return {key: value for key, value in doc['event_records'].items() if value['status'] == 'PENDING_REVIEW'}

if sys.argv[1] == 'capture':
    path = OUT / 'baseline.json'
    if path.exists():
        raise SystemExit('Baseline already exists')
    value = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             'sha256': hashes(), 'pending': pending(), 'allowed_changes': sorted(ALLOWED)}
    path.write_text(json.dumps(value, indent=2) + '\n')
elif sys.argv[1] == 'verify':
    base = json.loads((OUT / 'baseline.json').read_text())
    current = hashes()
    changed = [name for name, digest in base['sha256'].items() if current.get(name) != digest]
    result = {'all_protected_unchanged': not (set(changed) - ALLOWED),
              'protected_file_count': len(set(base['sha256']) - ALLOWED),
              'intentional_modified_files': sorted(set(changed) & ALLOWED),
              'unexpected_changes': sorted(set(changed) - ALLOWED),
              'phase51_acceptance_unchanged': all(current.get(k) == v for k, v in base['sha256'].items() if k.startswith('phase5_1_cloudflare_free/')),
              'pending_records_identical': base['pending'] == pending(), 'pending_count': len(pending())}
    (OUT / 'protected_files_verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    sys.exit(not result['all_protected_unchanged'] or not result['pending_records_identical'])
elif sys.argv[1] == 'python':
    sys.path.insert(0, str(ROOT))
    attempts = []
    def offline(event, args):
        if event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'http.client.connect', 'urllib.Request'):
            attempts.append(event)
            raise RuntimeError('OFFLINE_ONLY: ' + event)
    sys.addaudithook(offline)
    with (OUT / 'python_tests.log').open('w') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT)))
    value = {'total': result.testsRun, 'passed': result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
             'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped), 'network_attempts': attempts}
    (OUT / 'python_tests.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(value))
    sys.exit(not result.wasSuccessful() or bool(result.skipped) or bool(attempts))
