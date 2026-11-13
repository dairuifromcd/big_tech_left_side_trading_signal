"""Credential-free inspection of the last cf p51b-mock dry-run output."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CF = ROOT / 'cloudflare'
OUT = ROOT / 'phase5_1b_cloudflare_remote_mock'
BUILD = CF / '.cloudflare/output/v0'
config = json.loads((BUILD / 'workers/default/worker.config.json').read_text())
context = json.loads((BUILD / 'config.json').read_text())
meta = json.loads((CF / 'dist/remote-meta.json').read_text())
inputs = sorted(meta['inputs'])
source_map = json.loads((BUILD / 'workers/default/bundle/index.js.map').read_text())
bundles = BUILD / 'workers/default/bundle'
preparation = sys.argv[1:] == ['preparation']
mode = 'p51b-identity-prep' if preparation else 'p51b-mock'
assert context['buildContext']['mode'] == mode
assert config['name'] == 'us-stocks-p51b-mock-20261113'
assert config['exports'] == {'RemoteMockCoordinator': {'type': 'durable-object', 'storage': 'sqlite'}}
assert config['env']['REMOTE_MOCK_ENABLED']['value'] == 'DISABLED_PENDING_GATE_B'
assert set(config['env']) == {'COORDINATOR', 'REMOTE_MOCK_ENABLED', 'MOCK_START_UTC', 'MOCK_END_UTC', 'MOCK_INIT_END_UTC'}
assert {key: config['env'][key]['value'] for key in ['MOCK_START_UTC', 'MOCK_END_UTC', 'MOCK_INIT_END_UTC']} == ({
    'MOCK_START_UTC': '2026-11-15T22:00:00Z', 'MOCK_END_UTC': '2026-11-16T22:00:00Z',
    'MOCK_INIT_END_UTC': '2026-11-15T22:20:00Z'} if preparation else {
    'MOCK_START_UTC': '2026-11-15T23:00:00Z', 'MOCK_END_UTC': '2026-11-16T23:00:00Z',
    'MOCK_INIT_END_UTC': '2026-11-15T23:20:00Z'})
allowed = {'src/calendar-data.json', 'src/core.ts', 'src/integrity.ts', 'src/initialization.ts',
           'src/yahoo.ts', 'src/checkpoint.ts', 'src/storage.ts', 'src/api.ts', 'src/observations.ts',
           'src/coordinator.ts', 'src/synthetic.ts', 'src/remote-harness.ts', 'src/remote-worker.ts'}
assert set(inputs) == allowed
assert all(name.split('/src/')[-1] in {n.removeprefix('src/') for n in allowed} for name in source_map['sources'])
for path in [CF / 'src/remote-worker.ts', CF / 'src/remote-harness.ts', CF / 'src/synthetic.ts']:
    text = path.read_text()
    assert 'LOCAL_TESTING' not in text and 'scheduled(' not in text
    assert 'await fetch(' not in text and 'fetch(' not in text.replace('async fetch(', '')
assert not any(key in config for key in ['routes', 'assets', 'crons', 'triggers'])
files = sorted([*CF.glob('src/*'), *CF.glob('scripts/*'), *CF.glob('tests/*'),
                CF / 'cloudflare.config.ts', CF / 'package.json', CF / 'package-lock.json'])
hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in files if p.is_file()}
reviewed_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
(OUT / 'reviewed_code_sha256.json').write_text(json.dumps({'scope':'project Cloudflare source/config/lockfiles/scripts/tests; excludes secrets and generated outputs',
    'aggregate_sha256':reviewed_hash, 'sha256':hashes}, indent=2)+'\n')
result = {'status':'PASS_LOCAL_ONLY', 'cf_version':'1.0.0-beta.29', 'mode':mode,
    'remote_mutations':0,'deployments':0,'account_verification':'NOT_VERIFIED',
    'resources':{'worker':config['name'],'class':'RemoteMockCoordinator','storage':'sqlite','binding_count':1},
    'enabled':False,'secrets_present':False,'cron':False,'r2':False,'routes':False,'assets':False,
    'archived_yahoo_or_production_state_included':False,'esbuild_inputs':inputs,'vite_sources':source_map['sources'],
    'bundle_bytes':(bundles/'index.js').stat().st_size,
    'bundle_sha256':hashlib.sha256((bundles/'index.js').read_bytes()).hexdigest(),
    'worker_config_sha256':hashlib.sha256((BUILD/'workers/default/worker.config.json').read_bytes()).hexdigest(),
    'reviewed_code_sha256':reviewed_hash,'worker_config':config}
(OUT / ('preparation_build_audit.json' if preparation else 'remote_build_audit.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['worker_config','esbuild_inputs','vite_sources']}))
