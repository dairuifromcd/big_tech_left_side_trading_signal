"""Offline, project-only audit of complete cf Build Output. Never authenticates."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CF = ROOT / 'cloudflare'
OUT = ROOT / 'phase5_1b_cloudflare_remote_mock/stage1_local_package'
BUILD = CF / '.cloudflare/output/v0'
REMOTE = 'us-stocks-p51b-mock-20261113'
MODES = {'default': 'production', 'disabled_preparation': 'p51b-identity-prep',
         'disabled_stage2': 'p51b-mock', 'stage1': 'p51b-stage1'}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def hashes(root):
    assert not any(p.is_symlink() for p in root.rglob('*')), 'SYMLINK_NOT_ALLOWED'
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}

def aggregate(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def capture(label):
    assert label in MODES
    dest = OUT / 'builds' / label / '.cloudflare/output/v0'
    # An existing capture is re-audited in place, never overwritten by a later mode.
    if not dest.exists(): shutil.copytree(BUILD, dest)
    context = json.loads((dest / 'config.json').read_text())
    assert context == {'buildContext': {'isPreview': False, **({'mode': MODES[label]} if MODES[label] else {})}}
    workers = sorted((dest / 'workers').iterdir())
    assert [p.name for p in workers] == ['default']
    config = json.loads((workers[0] / 'worker.config.json').read_text())
    assert set(config) == {'name', 'compatibilityDate', 'compatibilityFlags', 'env', 'exports', 'manifest'}
    assert config['compatibilityDate'] == '2026-11-10'
    assert config['compatibilityFlags'] == ['nodejs_compat']
    assert config['manifest'] == {'type': 'partial', 'mainModule': 'index.js', 'modules': {}}
    if label == 'default':
        assert config['name'] == 'us-stocks-phase51-offline'
        assert config['exports'] == {'ExecutionCoordinator': {'type': 'durable-object', 'storage': 'sqlite'}}
        assert set(config['env']) == {'COORDINATOR'}
    else:
        assert config['name'] == REMOTE
        assert config['exports'] == {'RemoteMockCoordinator': {'type': 'durable-object', 'storage': 'sqlite'}}
        assert config['env']['COORDINATOR'] == {'type': 'durable-object', 'worker': REMOTE, 'exportName': 'RemoteMockCoordinator'}
        assert set(config['env']) == {'COORDINATOR', 'REMOTE_MOCK_ENABLED', 'MOCK_START_UTC', 'MOCK_END_UTC', 'MOCK_INIT_END_UTC'}
        assert config['env']['REMOTE_MOCK_ENABLED']['value'] == ('EXPLICIT_PHASE51B_IDENTITY_V1' if label == 'stage1' else 'DISABLED_PENDING_GATE_B')
        hour = '23' if label == 'disabled_stage2' else '22'
        for key, expected in {'MOCK_START_UTC': f'2026-11-15T{hour}:00:00Z', 'MOCK_END_UTC': f'2026-11-16T{hour}:00:00Z', 'MOCK_INIT_END_UTC': f'2026-11-15T{hour}:20:00Z'}.items():
            assert config['env'][key] == {'type': 'text', 'value': expected}
        allowed = {'calendar-data.json', 'core.ts', 'integrity.ts', 'initialization.ts', 'yahoo.ts', 'checkpoint.ts',
                   'storage.ts', 'api.ts', 'observations.ts', 'coordinator.ts', 'synthetic.ts', 'remote-harness.ts', 'remote-worker.ts'}
        source_map = json.loads((workers[0] / 'bundle/index.js.map').read_text())
        # Vite inlines calendar JSON without a sourcesContent entry.
        assert {p.split('/')[-1] for p in source_map['sources']} == allowed - {'calendar-data.json'}
        assert set(json.loads((CF/'dist/remote-meta.json').read_text())['inputs']) == {'src/'+n for n in allowed}
        bundle = (workers[0] / 'bundle/index.js').read_text()
        assert 'phase51b-synthetic-20261113-v1' in bundle
        assert not any(s in bundle for s in ['LOCAL_TESTING', 'testQuery', 'initializeLocalMock', 'AtomicityTest', 'inspect(){', 'query1.finance.yahoo.com', 'query2.finance.yahoo.com'])
        assert not any(s in bundle for s in ['LOCAL_ONLY_CONTROL_CREDENTIAL', 'LOCAL_ONLY_REPORT_CREDENTIAL'])
        # Validation of Yahoo-shaped synthetic data is allowed; network collection is not.
        assert 'fetch(' not in bundle.replace('async fetch(', '')
        assert 'scheduled(' not in bundle
    files = hashes(dest)
    expected_files = {'config.json', 'workers/default/worker.config.json', 'workers/default/bundle/index.js',
                      'workers/default/bundle/index.js.map', 'workers/default/bundle/.vite/manifest.json'}
    assert set(files) == expected_files, files
    write(f'{label}_output_inventory.json', {'status': 'PASS_LOCAL_ONLY', 'mode': MODES[label],
        'root': dest.relative_to(ROOT).as_posix(), 'files': files, 'aggregate_sha256': aggregate(files),
        'bundle_sha256': files['workers/default/bundle/index.js'], 'worker_config_sha256': files['workers/default/worker.config.json'],
        'bundle_bytes': (dest / 'workers/default/bundle/index.js').stat().st_size, 'worker_config': config,
        'workers_dev_preview_urls': 'UNSPECIFIED_CF_DEFAULTS_REVIEW_BEFORE_REMOTE_AUTHORIZATION',
        'remote_calls': 0})
    print(json.dumps({'label': label, 'files': len(files), 'aggregate_sha256': aggregate(files)}))

def verify():
    for label in MODES:
        inv = json.loads((OUT / f'{label}_output_inventory.json').read_text())
        assert hashes(ROOT / inv['root']) == inv['files']
    inv = json.loads((OUT / 'stage1_output_inventory.json').read_text())
    default = json.loads((OUT / 'default_output_inventory.json').read_text())
    assert default['bundle_sha256'] == json.loads((OUT.parent/'default_build_audit.json').read_text())['bundle_sha256']
    assert hashes(BUILD) == inv['files'], 'ACTIVE_OUTPUT_IS_NOT_REVIEWED_STAGE1'
    old = json.loads((OUT / 'disabled_preparation_output_inventory.json').read_text())
    a, b = old['worker_config'], inv['worker_config']
    delta = {k: {'disabled': a['env'][k], 'stage1': b['env'][k]} for k in a['env'] if a['env'][k] != b['env'][k]}
    assert set(delta) == {'REMOTE_MOCK_ENABLED'}
    aa, bb = dict(a), dict(b)
    aa.pop('env'); bb.pop('env'); assert aa == bb
    assert old['bundle_sha256'] == inv['bundle_sha256']
    assert inv['bundle_sha256'] == json.loads((OUT / 'disabled_stage2_output_inventory.json').read_text())['bundle_sha256']
    sources = {p.relative_to(ROOT).as_posix(): sha(p) for sub in ['src', 'tests', 'scripts'] for p in sorted((CF/sub).iterdir()) if p.is_file()}
    for name in ['cloudflare.config.ts', 'vite.config.ts', 'package.json', 'package-lock.json', 'tsconfig.json']:
        sources[f'cloudflare/{name}'] = sha(CF/name)
    write('source_sha256.json', {'scope': 'current Cloudflare sources, scripts, tests, config and lockfile',
        'sha256': sources, 'aggregate_sha256': aggregate(sources)})
    evidence = {p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and (p.suffix == '.log' or p.name.endswith('_results.json'))}
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    result = {'status': 'PASS_LOCAL_ONLY', 'mode': MODES['stage1'], 'head': git('rev-parse', 'HEAD'),
        'git_committed': False, 'source_sha256': aggregate(sources), 'bundle_sha256': inv['bundle_sha256'],
        'bundle_bytes': inv['bundle_bytes'], 'worker_config_sha256': inv['worker_config_sha256'],
        'complete_build_output_sha256': inv['aggregate_sha256'], 'complete_build_output': inv['root'],
        'lockfile_sha256': sha(CF/'package-lock.json'), 'historical_manifest_sha256': sha(OUT.parent/'deployment_manifest.json'),
        'package_manifest_sha256': sha(OUT/'package_manifest.json'),
        'evidence_sha256': evidence, 'evidence_aggregate_sha256': aggregate(evidence), 'configuration_delta_from_disabled_preparation': delta,
        'historical_bundle_changed': inv['bundle_sha256'] != json.loads((OUT.parent/'preparation_build_audit.json').read_text())['bundle_sha256'],
        'bundle_change_reason': 'Explicit identity-only flag and HTTP/RPC execution guards; strict Stage1 identity deadline and query rejection; existing full mock flag retained',
        'test_rpc_in_deployment': False, 'production_state_in_remote_graph': False, 'secret_bindings_in_build': [],
        'default_bundle_identical_to_historical_audit': True,
        'cf_version_locked': json.loads((CF/'package.json').read_text())['devDependencies']['cf'],
        'cf_version_installed': json.loads((CF/'node_modules/cf/package.json').read_text())['version'],
        'gate_b_approved': False, 'remote_mutations': 0}
    assert result['cf_version_locked'] == result['cf_version_installed'] == '1.0.0-beta.29'
    write('stage1_build_audit.json', result)
    print(json.dumps({k:result[k] for k in ['status','source_sha256','bundle_sha256','complete_build_output_sha256']}))

def check_release():
    # Read-only check for the future user: do not silently refresh approved hashes.
    release = json.loads((OUT/'release_inventory.json').read_text())
    for name, expected in release['sha256'].items():
        p = ROOT/name
        assert p.is_file() and sha(p) == expected, f'RELEASE_MISMATCH: {name}'
    for label in MODES:
        inv = json.loads((OUT/f'{label}_output_inventory.json').read_text())
        assert hashes(ROOT/inv['root']) == inv['files'], f'BUILD_OUTPUT_MISMATCH: {label}'
    audit = json.loads((OUT/'stage1_build_audit.json').read_text())
    assert sha(OUT/'package_manifest.json') == audit['package_manifest_sha256']
    # Submission may add a commit after the accepted local baseline. Exact released
    # file hashes above remain mandatory; ancestry does not replace content checks.
    subprocess.run(['git','merge-base','--is-ancestor',audit['head'],'HEAD'],cwd=ROOT,check=True)
    print('STAGE1_RELEASE_INTEGRITY: PASS_LOCAL_ONLY; NO_AUTH_OR_REMOTE_CALLS')

if __name__ == '__main__':
    if sys.argv[1] == 'capture': capture(sys.argv[2])
    elif sys.argv[1] == 'verify': verify()
    elif sys.argv[1] == 'check-release': check_release()
    else: raise SystemExit('capture <default|disabled_preparation|disabled_stage2|stage1>, verify, or check-release')
