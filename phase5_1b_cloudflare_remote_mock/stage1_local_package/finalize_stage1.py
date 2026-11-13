"""Generate local handoff evidence without changing any historical acceptance file."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
def read(n): return json.loads((OUT/n).read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v): (OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def md(n,v): (OUT/n).write_text(v.strip()+'\n')
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()

base=read('initial_baseline.json')
allowed={'cloudflare/cloudflare.config.ts','cloudflare/src/remote-worker.ts','cloudflare/scripts/local.mjs'}
new_code={'cloudflare/scripts/stage1_package_audit.py','cloudflare/tests/stage1-fixture.ts',
          'cloudflare/tests/stage1.test.ts','cloudflare/tests/stage1-runtime.test.ts'}
changed=[n for n,h in base['sha256'].items() if not (ROOT/n).is_file() or sha(ROOT/n)!=h]
unexpected=sorted(set(changed)-allowed)
untracked=git('ls-files','--others','--exclude-standard').splitlines()
unexpected_new=[n for n in untracked if n not in base['sha256'] and n not in new_code and not n.startswith('phase5_1b_cloudflare_remote_mock/stage1_local_package/')]
state=json.loads((ROOT/'phase4_2_four_20261104/state/monitor_state.json').read_text())
pending={k:v for k,v in state['event_records'].items() if v['status']=='PENDING_REVIEW'}
old=json.loads((OUT.parent/'baseline.json').read_text())
pending_hash=hashlib.sha256(json.dumps(pending,sort_keys=True,separators=(',',':')).encode()).hexdigest()
protected={'status':'PASS' if not unexpected and not unexpected_new else 'FAIL','head':git('rev-parse','HEAD'),
    'baseline':'initial_baseline.json; current HEAD plus pre-existing untracked research files',
    'protected_file_count':len(set(base['sha256'])-allowed),'unexpected_changes':unexpected,'unexpected_new_files':unexpected_new,
    'intentional_modified_files':sorted(changed),'new_code_files':sorted(new_code),
    'historical_phase51_phase51a_phase51b_and_research_preserved':not any(n.startswith(('phase5_1_cloudflare_free/','phase5_1a_hardening/','phase5_1b_cloudflare_remote_mock/')) for n in changed),
    'production_python_and_historical_market_state_preserved':not any(n.startswith(('src/','state/','phase4')) for n in changed),
    'pending_count':len(pending),'pending_sha256':pending_hash,'pending_records_identical':len(pending)==old['pending_count']==7 and pending_hash==old['pending_sha256']}
write('protected_files_audit.json',protected)
log=(OUT/'typescript_tests_authorized.log').read_text()
counts={n:int(re.search(r'^# '+n+r' (\d+)\s*$',log,re.M)[1]) for n in ['tests','pass','fail','cancelled','skipped','todo']}
assert counts['tests']==counts['pass']==380 and not any(counts[n] for n in ['fail','cancelled','skipped','todo'])
assert not (OUT/'typecheck.log').read_text().strip()
original_tests=[n for n in base['sha256'] if n.startswith('cloudflare/tests/')]
assert all(sha(ROOT/n)==base['sha256'][n] for n in original_tests)
assert protected['status']=='PASS' and protected['pending_records_identical'] and git('rev-parse','HEAD')==base['head']
node,runtime,full=(read(n) for n in ['stage1_node_results.json','stage1_workerd_results.json','stage1_full_output_workerd_results.json'])
assert all(j['status']=='PASS' and j['outbound_requests']==j['collector_calls']==0 and j['alarm'] is None for j in [node,runtime,full])
assert node['mutations']==0 and runtime['snapshot']['schema']==runtime['snapshot']['native']==[] and runtime['snapshot']['changes']==[{'n':0}]
parity=read('parity_results.json');hard=read('hardening_runtime_results.json');atomic=read('mock_start_atomicity_workerd_results.json')
assert parity['passed']==parity['golden_fixtures']==76 and parity['validation_fixtures']==32 and parity['compared_float_fields']==11145 and parity['max_absolute_difference']==0
assert hard['status']=='PASS' and hard['blocked_checkpoint_cases']==15 and hard['outbound_requests']==hard['collector_calls_for_blocked_cases']==0
assert atomic['status']=='PASS' and len(atomic['cases'])==19 and atomic['collector_calls']==atomic['outbound_requests']==0
for with_events in ['empty','events']:
    for platform in ['node','workerd']:
        result=read(f'idempotency_{platform}_{with_events}.json')
        assert result['snapshot_before_sha256']==result['snapshot_after_sha256']
assert read('runtime_results.json')['status']=='PASS'
for n,text in [('cf_default_build.log','Build complete'),('cf_stage1_build.log','Build complete'),
               ('cf_disabled_preparation_dry_run.log','--dry-run: exiting now.'),('cf_disabled_stage2_dry_run.log','--dry-run: exiting now.'),
               ('cf_stage1_prebuilt_dry_run.log','--dry-run: exiting now.'),('cf_packaged_prebuilt_dry_run.log','--dry-run: exiting now.')]:
    assert text in (OUT/n).read_text(),n
components={n:'PASS_LOCAL_ONLY' for n in ['DEFAULT_BUILD_DISABLED','STAGE1_IDENTITY_ENABLED','H01_INITIALIZATION_DISABLED',
    'MOCK_START_DISABLED_BEFORE_INITIALIZATION','UNAUTHORIZED_REQUESTS_REFUSED','EMPTY_SQL_AND_NATIVE_STORAGE',
    'ALARM_NULL','NO_EXTERNAL_COLLECTOR','WORKERD_SQLITE_TESTS','TYPESCRIPT_REGRESSION','GOLDEN_PARITY',
    'PROTECTED_FILES_INTEGRITY','BUILD_OUTPUT_AUDIT','DEPLOYMENT_RUNBOOK_READY']}
zero={n:0 for n in ['CLOUDFLARE_REMOTE_MUTATIONS','REMOTE_DEPLOYMENTS','OAUTH_LOGINS','API_TOKENS_CREATED',
    'REAL_SECRETS_CREATED','SECRETS_UPLOADED','REAL_YAHOO_REQUESTS','LIVE_TRADING_ACTIONS']}
result={'PHASE_5_1B_STAGE1_LOCAL_PACKAGE':'PASS','components':components,'typescript':{**counts,'baseline':285,'added':95,
    'baseline_retained':'All existing test files byte-identical; same original seven test modules executed; old baseline log unavailable in checkout',
    'baseline_test_files_sha256':{n:base['sha256'][n] for n in original_tests}},'typecheck':'PASS',
    'stage1_node':node,'stage1_workerd':runtime,'stage1_actual_cf_output_workerd':full,
    'runtime_test_binding_overrides':'workerd uses process-only fictitious Control/Report plus clock-relative start/end/initEnd; Node verifies exact candidate boundaries; candidate config text audited separately; no H01 injection except explicit denial probes',
    'full_output_standalone_test_count':43,'h01_h02_workerd':hard,'atomic_workerd_cases':19,
    'duplicate_start_idempotency':'PASS_NODE_AND_WORKERD_EMPTY_AND_EVENTS',
    'golden':{k:v for k,v in parity.items() if k!='results'},
    'python':'ACCEPTED_HISTORICAL_271/271; not rerun; no Python or common business logic changes',
    'local_build_and_prebuilt_dry_run':'PASS; exact packaged working directory validated without rebuilding',
    'initial_failures_retained':['typescript_tests.log (sandbox loopback EPERM)',
        'typescript_initial_test_harness_failure.log (sync esbuild plugin / RPC proxy comparison)',
        'typescript_rpc_sync_failure.log (missing RPC throws synchronously)'],
    'protected_files':protected,**zero,'GATE_B_APPROVED':False,'cloud_platform_behavior':'NOT_VERIFIED'}
write('stage1_test_results.json',result)
subprocess.run(['python3',str(ROOT/'cloudflare/scripts/stage1_package_audit.py'),'verify'],cwd=ROOT,check=True)
audit=read('stage1_build_audit.json');inv=read('stage1_output_inventory.json')
status_table='\n'.join(f'| `{k}` | {v} |' for k,v in components.items())
zero_text='\n'.join(f'{k}: {v}' for k,v in zero.items())+'\nGATE_B_APPROVED: false'

md('stage1_acceptance.md',f'''
# Stage 1 本地部署包验收

PHASE_5_1B_STAGE1_LOCAL_PACKAGE: **PASS**（仅本地准备，2026-11-13 Australia/Brisbane）。
Git HEAD `{base['head']}`；无提交、推送、登录、远程部署或云资源创建。原Manifest与9份研究文件均保持原字节。

| 分项 | 结果 |
|---|---|
{status_table}

完整TS380/380（285原有+95新增；零跳过/取消/TODO），typecheck通过。Stage1 Node51、观测型workerd42；另用实际cf产物workerd42项检查（独立运行含父测试43/43）。H01/H02、事务原子性19个workerd场景、两种状态的Node/workerd重复启动、Golden76+32验证/11145数值字段最大差异0均通过。Python未修改，沿用已验收271/271。初次沙箱监听失败和测试适配失败日志保留，最终全通过。

workerd执行真实Bundle与SQLite，但在本地进程注入虚构Control/Report及相对当前时钟的三项窗口绑定；没有等待真实候选日期或修改主机时钟。候选配置的三个固定UTC文本单独静态审计，Node注入时钟验证精确边界。此模拟不证明候选时刻云端行为。

Identity每次检查SQL/native为空、Alarm=null、initialized=false；Node记录0条写入/事务/sync/Alarm变更，workerd观察schema=[]/total_changes=0/native=[]/collector=0。无应用schema即无Receipt、Run、Claims和STOPPED记录。Stage1所有非Identity HTTP/RPC在状态访问前拒绝；原H01代码及开关规则未削弱。

完整cf Build Output：`{inv['root']}`，5个文件（含隐藏`.vite/manifest.json`、source map、root config、worker config与JS）。不是单独esbuild Bundle。源图仅13个合成/规则模块（JSON不出现在Vite source map），没有本地RPC、生产状态、Yahoo网络采集器或凭据。默认包与原验收Bundle哈希完全相同。

| 哈希对象 | SHA-256 |
|---|---|
| 当前源/配置/测试/脚本聚合 | `{audit['source_sha256']}` |
| Stage1 JS（{audit['bundle_bytes']} bytes） | `{audit['bundle_sha256']}` |
| Worker配置 | `{audit['worker_config_sha256']}` |
| 完整Build Output清单聚合 | `{audit['complete_build_output_sha256']}` |
| 依赖锁 | `{audit['lockfile_sha256']}` |
| 原Manifest（未改） | `{audit['historical_manifest_sha256']}` |
| Stage1 package_manifest.json | `{audit['package_manifest_sha256']}` |
| 测试证据清单聚合 | `{audit['evidence_aggregate_sha256']}` |

聚合算法是排序路径→文件SHA256映射的紧凑JSON再SHA256；单文件完整清单见各output_inventory.json、source_sha256.json及stage1_build_audit.json。release_inventory.json记录最终交付文件及代码的逐文件哈希，不自我包含。未来使用`check-release`只读核验，不运行会刷新hash的`verify`来代替审批。

本地PASS不证明实际账户权限、SQLite首创、Secret激活、URL传播或计费成功。建议提交**仅用户人工首次部署**的单独授权审阅；不建议现在执行。不足以在候选窗口前完成授权/核验就推迟，不自动扩窗。

```text
{zero_text}
```
''')

md('stage1_security_matrix.md','''
# Stage 1 实际可达路径与安全矩阵

证据：stage1_node_results.json（51 checks）、stage1_workerd_results.json（42 checks）、stage1_full_output_workerd_results.json（实际cf Bundle42 checks），完整TS日志。所有测试凭据使用测试进程randomBytes，既不记录值，也不进入源码常量、Manifest或部署Bundle；没有真实Secret。

| 路径 / 能力 | Stage1实际行为 | 拒绝与无副作用证据 |
|---|---|---|
| GET /_mock/identity | 只有专用Control Bearer、合法窗口、无query返回200 | 固定getByName；initialized=false、empty_sql/native=true、Alarm=null |
| Identity缺失/错误/Bearer格式错误/Report冒充Control | 403通用错误 | HTTP逐一测试；不创建表或Alarm |
| 配置缺失/过短Control | 403；直接RPC拒绝 | Node及workerd；不生成新凭据 |
| 默认、既有prep、Stage2禁用模式 / 未知enable | Identity不可用 | 构建配置精确审计，Node禁用值和workerd禁用模式测试 |
| Identity对象ID、namespace、SQL、fixture、token query | 403 | 不选择任意对象、不执行query SQL；Node路由桩断言固定名称 |
| POST Identity | 405 | 无写入 |
| POST /_mock/initialize | 403；直接RPC STAGE1_IDENTITY_ONLY | 即使误注入完整H01字段也拒绝；正式包3项H01绑定均缺席 |
| POST /_mock/start，固定或任意fixture | 403；直接RPC拒绝 | 无Run/Claims/预算/任务/Alarm；不接受任意日期 |
| POST /_mock/stop | 403；直接RPC拒绝 | 不伪造STOPPED，不执行sync/deleteAlarm |
| GET /_mock/status | 403；直接RPC拒绝 | 不读取/泄露实验、Receipt或数据；不创建schema |
| 六类GET /api/*报告 | 正确Report仍403；无/错Report401 | Stage1禁用report RPC，API数据不可达 |
| POST /api/* | 有效Report405；无有效凭据401 | 不执行API写入 |
| 未知管理、对象路径、SQL入口 | 403 | 没有任意SQL/本地测试RPC；workerd缺失方法实际拒绝 |
| Direct RPC identity | 同样Control和时间守卫 | HTTP不能提供其他DO/namespace；绑定属于固定Worker |
| Alarm callback | Stage1立即返回 | Node调用真实alarm()确认零状态/Alarm操作；无HTTP Alarm入口 |
| 真实Yahoo / 交易 / 正式监控 | 不可达 | Stage1只读；合成collector calls=0，outbound=0；远程源图无网络collector |

Node精确时钟验证start-1拒绝、start允许、initEnd后仍可Identity、end-1允许、end及以后拒绝；Stage1没有Stage2的额外1h控制宽限。workerd通过配置窗口重载验证开始前及结束后拒绝，再回到原窗口读空状态。重复Identity、DO适配器替换和workerd进程dispose/recreate后ID不变、空状态不变。workerd模拟重启不等于真实云端eviction。

Node将所有非SELECT SQL、事务、sync、set/deleteAlarm计为mutations；所有检查后均0。workerd本地专用观察类检查全部应用sqlite_master、total_changes()、native和Alarm；它只存在于内存测试构建，未进入cf产物。实际cf Bundle另行执行同一HTTP/RPC拒绝与身份/重启检查，部署包没有观察RPC。内部SQL查询是固定代码，不接受HTTP SQL字符串。

Stage1是显式能力限制；Stage2仍使用原EXPLICIT_PHASE51B_MOCK_V1并保留原H01+Receipt+checkpoint+持久化窗口守卫，原回归全通过。默认src/worker.ts及Python策略不变。
''')

md('stage1_configuration_diff.md',f'''
# 配置精确差异与Bundle重新验收

唯一启用方式：本地显式`node cloudflare/scripts/local.mjs stage1-build`（内部cf build --mode p51b-stage1）。不能把现有p51b-identity-prep当启用包。没有凭据仍拒绝Identity。

| 字段 | 原禁用prep / 当前disabled_preparation | Stage1 |
|---|---|---|
| mode（root buildContext） | p51b-identity-prep | p51b-stage1 |
| env.REMOTE_MOCK_ENABLED.value | DISABLED_PENDING_GATE_B | EXPLICIT_PHASE51B_IDENTITY_V1 |
| entrypoint | src/remote-worker.ts | 相同 |
| Worker | us-stocks-p51b-mock-20261113 | 相同 |
| export / storage | RemoteMockCoordinator / sqlite | 相同 |
| COORDINATOR | 同Worker/exportName | 相同 |
| start / end / initEnd | 11-15 22:00 / 11-16 22:00 / 11-15 22:20 UTC | 相同 |
| compatibilityDate / flags | 2026-11-10 / nodejs_compat | 相同 |
| H01 flag / ID / init Secret | 缺席 | 缺席 |
| Control / Report Secret | 构建中缺席 | 构建中缺席；未来用户独立配置 |
| Cron/R2/Routes/Custom Domain/额外Worker或class | 无 | 无 |
| workersDev / previewUrls | 未显式指定 | 同样未指定；默认效果须用户未来审阅 |

程序逐字段断言Worker配置仅一个env值不同，两个root config只有mode不同；当前两个remote禁用模式和Stage1的JS字节完全相同。Stage1与disabled Stage2配置还相差三项时间（Stage2仍23:00/23:00/23:20），没有自动将Stage2启用。

相对历史HEAD远程Bundle由156016变为{audit['bundle_bytes']} bytes；旧hash `4dd23002f2548f7d29035fdfa10d5e26cf3e5a1c7769786bac88ab6671da8976`，新hash `{audit['bundle_sha256']}`。原因是加入identity专用enable值、HTTP/RPC副作用拒绝、Stage1精确截止与Identity query拒绝。重新通过380/380及实际cf Bundle workerd42项检查，未沿用旧hash。Stage2完整enable值/H01/持久化设计不变；Stage2也会包含这些已验收守卫代码。

默认production包仍使用src/worker.ts，没有remote enable/init/test/report Secret绑定；Bundle hash仍为历史`4fa3f652a0a585c21885ea6a6422f58f4b0de6971f21c01604be4c7b566b2f49`。正式执行入口和Python市场逻辑未改。

四种模式的完整输出各自留存在builds/下，源目录最后活动输出为Stage1。用户未来从builds/stage1执行--prebuilt，避免其他mode构建覆盖共用活动目录；该独立目录已完成无凭据dry-run。
''')

md('stage1_deployment_runbook_draft.md',f'''
# 用户人工首次部署草案（未授权）

USER_LOCAL_CF_BOOTSTRAP · NOT_AUTHORIZED_TO_EXECUTE · GATE_B_APPROVED: false。
本轮只准备包，以下任何认证、凭据、Secrets、云部署、Identity请求和撤销均须后续单独批准，且由用户在独立Mac Terminal操作；Codex不接触值、不操作该Terminal。不将整份草案当自动脚本执行。

## 执行前决策与核验

1. 用户Dashboard重新确认目标账户、Workers Free、既有workers.dev、当前Workers/DO共享额度和计量窗口。记录核验时刻与脱敏账户引用。确认只允许一个Worker/一个SQLite namespace/固定实例；无升级、费用或新账户子域注册。实际套餐和配额仍NOT_VERIFIED；历史Free报告不代表当前状态。
2. 确认`us-stocks-p51b-mock-20261113`尚不存在，检查DO namespace与共享用量。若同名、现有资源归属不明或需要额外资源则停止，不能覆盖或换名重建。不访问property-profit-au的代码、Secret、业务URL或修改它；仅用户用已有Dashboard权限核对资源列表变化。
3. 审阅完整包和本轮新hash，不拿旧Manifest当执行授权。入口remote-worker.ts、exports RemoteMockCoordinator/sqlite、COORDINATOR同Worker/class、固定名phase51b-synthetic-20261113-v1；H01三项缺席、无Cron/R2/Routes/custom domain/额外Worker。workersDev/previewUrls未显式配置，cf可能应用默认设置，须用户审阅目标Worker预期默认效果；若要求创建账户子域或有意外效果停止。
4. 单独批准账户、一次首创部署尝试、公开workers.dev入口/预览默认效果、SQLite namespace协调、两个应用Secret、Identity核验、共享额度风险与撤销方案。首创短期Workers产品Admin能影响账户其他Workers，不能限定尚不存在的新名称；只由用户持有。建议30–60min TTL，确切not_before/expires_on由未来授权决定，不申请其他账户/产品或Token管理权限。
5. 两个独立Control/Report Secret至少32随机字节，未来经单独批准由用户自己生成；本轮没有生成。用户未来选择项目cloudflare/.tmp/p51b-stage1-secrets.json（被忽略，权限0600），JSON仅两个键MOCK_CONTROL_TOKEN、REPORT_TOKEN；不含控制面Token或init键，不发送聊天/截图，不提交。明文同OS用户隔离有限；更安全替代是用户Dashboard输入，但可能增加Version/Deployment，必须先重审。未经另批不执行任何生成/上传/撤销。
6. 候选Identity Brisbane 2026-11-16 08:00–08:15，UTC start11-15 22:00/end11-16 22:00/initEnd11-15 22:20；只Identity，不初始化。若准备不足推迟，不能自动扩窗。Stage2/Gate B另外授权，当前p51b-mock仍禁用；不得顺势第二次部署。

## 完整包本地只读核对

未来用户可从项目根执行以下**只读**核验；它不刷新批准hash：

```sh
python3 cloudflare/scripts/stage1_package_audit.py check-release
```

比对stage1_build_audit.json、stage1_output_inventory.json与本验收报告；完整5文件清单、源码/锁/Manifest/测试证据SHA须匹配。完整包聚合`{audit['complete_build_output_sha256']}`；JS `{audit['bundle_sha256']}`；worker.config `{audit['worker_config_sha256']}`。任何差异停止，不运行verify刷新hash来掩盖差异，不在有凭据时重建。

## 用户未来独立终端（全部未授权）

下列本地变量不改全局配置，Token隐藏读取且不写shell历史。不启用set -x/DEBUG，不读取个人Profile/Keychain，不OAuth、不安装工具。相同macOS用户不是硬隔离；严格隔离设备/用户方案须另行批准，服务端撤销是关闭高权限的关键。

```sh
# NOT_AUTHORIZED_TO_EXECUTE — USER LOCAL CREDENTIAL SETUP
P51B_CF='{ROOT}/cloudflare'
P51B_PKG='{OUT}/builds/stage1'
read 'P51B_ACCOUNT?Approved account ID (local only): '
read -rs 'P51B_TOKEN?Approved short-lived bootstrap token (hidden): '
print
cfp() {{
  test -n "$P51B_ACCOUNT" && test -n "$P51B_TOKEN" || return 1
  env -i PATH="$P51B_CF/node_modules/node/bin:$P51B_CF/node_modules/.bin:/usr/bin:/bin" \\
    TMPDIR="$P51B_CF/.tmp" XDG_CONFIG_HOME="$P51B_CF/.home" XDG_CACHE_HOME="$P51B_CF/.cache" \\
    CF_SEND_TELEMETRY=0 DO_NOT_TRACK=1 CI=true NO_UPDATE_NOTIFIER=1 \\
    CLOUDFLARE_ACCOUNT_ID="$P51B_ACCOUNT" CLOUDFLARE_API_TOKEN="$P51B_TOKEN" \\
    "$P51B_CF/node_modules/node/bin/node" "$P51B_CF/node_modules/cf/bin/cf" "$@"
}}
cd "$P51B_PKG"

# NOT_AUTHORIZED_TO_EXECUTE — REMOTE WRITE / ONE FIRST DEPLOYMENT ATTEMPT
cfp deploy --prebuilt --mode p51b-stage1 --provision=false \\
  --secrets-file "$P51B_CF/.tmp/p51b-stage1-secrets.json"
```

准确使用项目已安装cf1.0.0-beta.29/Node22.23.0；该cwd的prebuilt dry-run已在本轮通过。--provision=false不阻止Worker/exports namespace/目标子域设置写入。无create-only原子保护：临近重查名称；失败也计一次尝试，先核对部分创建情况，不能自动重跑、加force、provision=true、migration或扩权。无需也不允许创建另一个DO class/测试实例。

## 部署后人工核验、Identity与撤销

用户Dashboard确认活动Version/Deployment、唯一Worker、RemoteMockCoordinator为SQLite、namespace归属正确、COORDINATOR同namespace，无意外Cron/R2/Route/domain/其他Worker；记录真实workers.dev URL与时间。Secrets仅检查名称，不回传值；实际Secret激活语义尚未验证，命令成功不等于活动版本正确。

用户在候选窗口内，仅发送`GET /_mock/identity`，Control在Bearer Header中；不把Secret放URL、命令参数或日志。不调用initialize/start/stop/status/report或SQL。Identity会唤起DO实例，虽应用只读，也属于未来须批准的云操作。以下草案只允许一次请求、拒绝重定向、只输出经校验的身份字段；由用户未来获批后亲自在自己的Terminal执行，Codex本轮不运行、不读取Secret文件：

```sh
# NOT_AUTHORIZED_TO_EXECUTE — REMOTE IDENTITY RPC / USER TERMINAL ONLY
read 'P51B_ORIGIN?Exact approved workers.dev origin from Dashboard: '
python3 - "$P51B_ORIGIN" "$P51B_CF/.tmp/p51b-stage1-secrets.json" <<'P51B_IDENTITY_PY'
import json, re, sys, urllib.request, urllib.parse, urllib.error
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
try:
    origin = urllib.parse.urlsplit(sys.argv[1])
    assert origin.scheme == 'https' and origin.port in (None, 443)
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    assert origin.path in ('', '/')
    assert re.fullmatch(r'us-stocks-p51b-mock-20261113\\.[a-z0-9-]+\\.workers\\.dev', origin.hostname or '')
    with open(sys.argv[2]) as source:
        values = json.load(source)
    assert set(values) == {{'MOCK_CONTROL_TOKEN', 'REPORT_TOKEN'}}
    credential = values['MOCK_CONTROL_TOKEN']
    assert isinstance(credential, str) and len(credential) >= 32
    target = urllib.parse.urlunsplit(('https', origin.netloc, '/_mock/identity', '', ''))
    req = urllib.request.Request(target, headers={{'Authorization': 'Bearer ' + credential}}, method='GET')
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=10) as response:
        assert response.status == 200
        body = response.read(4097)
    assert len(body) <= 4096
    value = json.loads(body)
    assert set(value) == {{'object_id', 'initialized', 'empty_sql', 'empty_native', 'alarm'}}
    assert re.fullmatch('[0-9a-f]{{64}}', value['object_id'])
    assert value['initialized'] is False and value['empty_sql'] is True
    assert value['empty_native'] is True and value['alarm'] is None
    print(json.dumps(value, sort_keys=True))
except urllib.error.HTTPError as error:
    print('IDENTITY_REFUSED_HTTP_STATUS', error.code)
    sys.exit(1)
except Exception:
    print('IDENTITY_CHECK_FAILED_STOP_NO_RETRY')
    sys.exit(1)
P51B_IDENTITY_PY
```

本地仅做以上脚本语法审阅，没有联网验证用户请求片段。保留首次成功结果，若批准重复核对则由用户再次手动运行一次；无自动循环或重试。HTTP错误不打印响应头、凭据或完整异常。

必须得到object_id（远程实际值）、initialized=false、empty_sql=true、empty_native=true、alarm=null；重复一次核对同ID。保存脱敏JSON、namespaceID/绑定对应证据。**本地workerd测试ID不可用于Stage2**。SQL空且initialized=false说明没有应用schema/Receipt/Run/Claims；不创建表来“查Receipt”。任何不符合都停止，不删除重建、不初始化。异步传播/身份/权限不确定时推迟，不抢窗口。

首创控制面核验后尽快在Dashboard服务端撤销本任务Admin Token，确认撤销状态；Identity用应用Control，不需要Admin。必要的旧Token只读失效检查须另批且只对专用目标，不拿其他Worker作探测。然后本地释放：

```sh
# NOT_AUTHORIZED_TO_EXECUTE — LOCAL CREDENTIAL RELEASE AFTER SERVER REVOCATION
unset P51B_TOKEN P51B_ACCOUNT
```

用户关闭终端、确认无持有高权限的任务进程。不logout影响既有个人配置。之后若需要Stage2，另批仅目标Worker的Individual Worker Editor；全cf链路兼容NOT_VERIFIED，缺权停止，不把Admin交给Codex兜底。

Stage1保留Control/Report能力必须有批准的短时计划；未继续Stage2则按批准撤销应用Secrets并确认活动版本已失效。未来可审核以下名称级批量撤销，**不在本轮运行**：

```sh
# NOT_AUTHORIZED_TO_EXECUTE — REMOTE WRITE / CREATES SECRET VERSION
cfp workers secrets bulk --worker us-stocks-p51b-mock-20261113 \\
  --secrets '{{"MOCK_CONTROL_TOKEN":null,"REPORT_TOKEN":null}}'
```

此命令需要用户另批的目标Worker授权，不能在Admin已撤销且未重新授权时执行。若只生成Version未激活，停止并重审激活操作，不加bypass或盲目第三次部署。用户Dashboard删除并Deploy也是远程写入、须另批；记录额外Version/Deployment。unset不是服务端撤销。未初始化时Stop被设计拒绝，不能宣称STOPPED；处置为停止操作、撤销应用Secrets/临时Token、保留空资源。删除云资源另批。

## 停止条件与回传

任何额外权限/账户元数据范围、收费/升级、子域注册、资源差异、SQLite协调失败、名称冲突、hash不符、绑定/ID不符、Secret激活未知或时间不足：立即停止，保存脱敏错误码/请求ID/时间、核对部分创建，撤销可撤销授权并保留现场。撤销不回滚数据；不改其他项目，不扩权，不删除DO或重建。未能确认撤销时如实报告能力可能仍有效。

回传仅cf版本、核对hash、Worker名、脱敏账户引用、活动版本/Deployment/namespace对应关系、实际ID与空状态、错误码/时刻、撤销结果。不要回传任何Token、Secret JSON、Authorization、Profile或shell变量。实际权限、SQLite首创、Secret激活、传播和云端成本仍NOT_VERIFIED。
''')

md('stage1_risks_and_open_questions.md','''
# 剩余风险与未验证事项

本地包PASS，远程执行未授权；没有新开展大范围部署研究，依据已有9份研究与锁定本地cf源码/实际构建验证。

| 未决事项 | 当前边界 / 后续停止条件 |
|---|---|
| 首次Workers Admin授权范围 | 尚不存在的Worker不能按名称限制Admin；只由用户持有、短TTL并立即服务端撤销 |
| beta29真实SQLite exports首创 | 本地声明/Miniflare SQLite通过；--provision=false下真实平台协调仍NOT_VERIFIED，失败停止，不补migration/扩权 |
| 实际账户/Free/额度 | 无账户API调用；历史Dashboard报告不能代表临近余额，无零费用保证；收费/升级提示停止 |
| workers.dev与previewUrls默认 | 包保持既有未显式配置；可能写目标Worker默认设置，须用户确认已有子域和接受精确效果；不能自动注册账户子域 |
| 名称首次创建竞态 | 无已证明原子create-only flag；部署前人工再查，同名即停止 |
| Secret上传、Version与激活/撤销 | 生成版本不保证切换流量；逐次核验活动版本，任何额外激活另批；不能把省略键当撤销 |
| 单Worker Editor整条CLI依赖 | 尚未端到端实证；额外权限403即停止，不扩权或将Admin交代理 |
| ID/namespace跨Stage2稳定性 | 本地重启一致；云端必须相同账户/Worker/class/namespace/固定名实证。测试ID绝不用于云端 |
| 同OS用户凭据隔离 | 用户独立Terminal是操作边界，非硬隔离；不让Codex接触值，服务端撤销；更强隔离另批 |
| 真实CPU/Alarm/SQL/计费 | 本地workerd不能证明云端Free CPU或配额；Stage1没有应用Alarm，未测实际Alarm服务 |
| 候选时间可行性 | Brisbane11-16 08:00–08:15核验；准备/授权不充分就推迟，不自动扩窗；Stage1 Identity硬截止11-17 08:00，无额外宽限 |
| Stage2独立批准 | Stage1不能initialize/start/stop/status/report；现有Stage2仍禁用，必须另审精确ID/H01/Secrets/完整包与Gate B |

Stage1模式刻意在HTTP及RPC双层拒绝副作用，即使有人误注入H01字段仍不启用。所有远程源码包含Stage2内部规则实现，但没有本地测试RPC或任意SQL入口。默认生产入口与Python未改变，原安全机制没有通过禁用来让测试通过。

建议：本包可提交“用户人工首次部署”的独立授权审阅，先解决账户、TTL、默认URL效果、Secrets激活/撤销和一次尝试账本；这不是授权，也不是云端可行性保证。若来不及完成，推迟候选实验。
''')

changed_lines='\n'.join('- `'+n+'`' for n in sorted(allowed|new_code))
md('stage1_completion_handoff.md',f'''
# Stage 1 完成交接

PHASE_5_1B_STAGE1_LOCAL_PACKAGE: **PASS_LOCAL_ONLY**。本次工作完成后停止，未提交Git、未推送、未部署。

1. 实际Git HEAD `{git('rev-parse','HEAD')}`，与输入基线一致。进入时仅9份first_deployment_feasibility研究文件未跟踪；保持原字节。现在3个tracked文件修改，4个新增代码/测试文件及本stage1_local_package新增交付。完整清单见changed_files.json（含被Git忽略的构建证据），工作区未提交。
2. Stage1显式mode为`p51b-stage1`，REMOTE_MOCK_ENABLED=EXPLICIT_PHASE51B_IDENTITY_V1；缺省、p51b-identity-prep、p51b-mock均没有启用远程Mock。Stage1无H01 flag/对象ID/init Secret，Control/Report未来另批注入，本轮没有真实Secret。
3. 唯一有用HTTP能力是GET /_mock/identity；固定实例、专用Control Bearer、无query、窗口内。其他管理/报告入口在Stage1仍存在于路由/代码中但HTTP/RPC均拒绝，无初始化/Run/Claims/STOPPED/Alarm或数据泄露。原Full Mock flag与H01设计保留。详见stage1_security_matrix.md。
4. TS380/380（原285全部保留、+95，无跳过），typecheck通过；Stage1 Node51/workerd42；实际cf Bundle另42检查（独立43/43含父测试）。H01/H02包括15损坏状态请求前阻断、原子启动19workerd场景、重复启动Node/workerd两状态、local SQLite/重启、Golden76+32/11145字段最大差异0全通过。Python规则/公共逻辑未改，沿用已验收271/271而非宣称本轮重跑。所有初始失败日志保留。
5. 完整Build Output为`{inv['root']}`，5文件SHA逐项列在stage1_output_inventory.json；独立cwd --prebuilt dry-run及真实Bundle workerd均通过。聚合 `{audit['complete_build_output_sha256']}`，JS `{audit['bundle_sha256']}`（{audit['bundle_bytes']} bytes），Worker config `{audit['worker_config_sha256']}`。源/锁/Manifest/证据哈希见stage1_build_audit.json，全部当前重算。
6. 相对原禁用prep，生成Worker配置只有enable值差异，root mode另变；三项准备窗口保持。历史Bundle因最小Stage1守卫代码变更已重新验收；当前所有remote模式Bundle相同。默认production Bundle与历史hash完全一致。无Cron/R2/Route/domain、额外Worker/class或身份变更。
7. 两阶段设计保留：Stage2 p51b-mock仍禁用，未来固定实际ID、H01 flag/init Secret及最终窗口均须另审完整包并另批Gate B。Stage1不赋予Stage2执行权，不扩展持久化时间或修改7条PENDING_REVIEW。
8. 用户未来必须独立批准：指定账户/Free和共享额度、短期账户Workers产品Admin及TTL（仅用户持有）、一次首创Worker/SQLite exports/Binding/默认URL设置、两个应用Secret生成和上传、固定Identity核验、服务端撤销与必要Secret版本激活。后续窄Editor和Stage2/Gate B分别另批。具体资源、外部影响、风险、恢复与替代见runbook。
9. Cloudflare实际权限、首次SQLite协调、单Worker Editor完整CLI链、Secret活动版本/撤销语义、真实URL传播/ID稳定性、CPU/SQL/Alarm和费用仍NOT_VERIFIED。默认保留资源，未初始化不能伪称STOPPED；异常停止并撤销批准的能力，不自动删除重建。
10. **建议申请仅用户人工首次部署的单独授权审阅**，不建议现在运行；候选Brisbane11-16 08:00–08:15若无法完成准备就推迟，不自动延长。GATE_B_APPROVED保持false。

## 代码变更全清单

{changed_lines}

新增交付至少8份要求文件，另有完整四种构建输出、逐文件hash、不可变初始基线、保护审计、测试结果/日志、package_manifest和只读release校验。原历史验收文件未更新。{protected['protected_file_count']}个受保护基线文件完整，7条PENDING_REVIEW哈希一致。

```text
{zero_text}
```
''')

# Include ignored build files and logs, not only Git's short status.
deliverables={p.relative_to(ROOT).as_posix() for p in OUT.rglob('*') if p.is_file()}
deliverables.update((OUT/n).relative_to(ROOT).as_posix() for n in ['changed_files.json','release_inventory.json'])
changes={'head':git('rev-parse','HEAD'),'git_status':git('status','--short'),
    'modified_tracked':sorted(changed),'new_code':sorted(new_code),
    'new_deliverables':sorted(deliverables),
    'pre_existing_untracked_preserved':[n for n in base['sha256'] if n.startswith('phase5_1b_cloudflare_remote_mock/first_deployment_feasibility/')]}
write('changed_files.json',changes)
release_files={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='release_inventory.json'}
release_files.update({n:sha(ROOT/n) for n in sorted(allowed|new_code)})
write('release_inventory.json',{'scope':'All Stage1 deliverables and changed code; excludes this self-referential inventory',
    'head':git('rev-parse','HEAD'),'sha256':release_files})
print(json.dumps({'status':'PASS_LOCAL_ONLY','typescript':counts,'protected':protected['protected_file_count'],
    'deliverable_files':len(release_files),'gate_b_approved':False},ensure_ascii=False))
