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

比对stage1_build_audit.json、stage1_output_inventory.json与本验收报告；完整5文件清单、源码/锁/Manifest/测试证据SHA须匹配。完整包聚合`9d905d8da36bf5602dadbda25280d0fc4504d7a9b73d06dfc5cbb1bfd654ed39`；JS `f750138982c60fdca94c47fea14a5d93c47d03a0daeb154795c0a1a275caf7a6`；worker.config `bfca973a1f48aefc457fe27e7685ee110e8b10985997d25421279d3ced9712c4`。任何差异停止，不运行verify刷新hash来掩盖差异，不在有凭据时重建。

## 用户未来独立终端（全部未授权）

下列本地变量不改全局配置，Token隐藏读取且不写shell历史。不启用set -x/DEBUG，不读取个人Profile/Keychain，不OAuth、不安装工具。相同macOS用户不是硬隔离；严格隔离设备/用户方案须另行批准，服务端撤销是关闭高权限的关键。

```sh
# NOT_AUTHORIZED_TO_EXECUTE — USER LOCAL CREDENTIAL SETUP
P51B_CF='/Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal/cloudflare'
P51B_PKG='/Users/rui/Documents/fun_projects/vibe_coding/big_tech_left_side_trading_signal/phase5_1b_cloudflare_remote_mock/stage1_local_package/builds/stage1'
read 'P51B_ACCOUNT?Approved account ID (local only): '
read -rs 'P51B_TOKEN?Approved short-lived bootstrap token (hidden): '
print
cfp() {
  test -n "$P51B_ACCOUNT" && test -n "$P51B_TOKEN" || return 1
  env -i PATH="$P51B_CF/node_modules/node/bin:$P51B_CF/node_modules/.bin:/usr/bin:/bin" \
    TMPDIR="$P51B_CF/.tmp" XDG_CONFIG_HOME="$P51B_CF/.home" XDG_CACHE_HOME="$P51B_CF/.cache" \
    CF_SEND_TELEMETRY=0 DO_NOT_TRACK=1 CI=true NO_UPDATE_NOTIFIER=1 \
    CLOUDFLARE_ACCOUNT_ID="$P51B_ACCOUNT" CLOUDFLARE_API_TOKEN="$P51B_TOKEN" \
    "$P51B_CF/node_modules/node/bin/node" "$P51B_CF/node_modules/cf/bin/cf" "$@"
}
cd "$P51B_PKG"

# NOT_AUTHORIZED_TO_EXECUTE — REMOTE WRITE / ONE FIRST DEPLOYMENT ATTEMPT
cfp deploy --prebuilt --mode p51b-stage1 --provision=false \
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
    assert re.fullmatch(r'us-stocks-p51b-mock-20261113\.[a-z0-9-]+\.workers\.dev', origin.hostname or '')
    with open(sys.argv[2]) as source:
        values = json.load(source)
    assert set(values) == {'MOCK_CONTROL_TOKEN', 'REPORT_TOKEN'}
    credential = values['MOCK_CONTROL_TOKEN']
    assert isinstance(credential, str) and len(credential) >= 32
    target = urllib.parse.urlunsplit(('https', origin.netloc, '/_mock/identity', '', ''))
    req = urllib.request.Request(target, headers={'Authorization': 'Bearer ' + credential}, method='GET')
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=10) as response:
        assert response.status == 200
        body = response.read(4097)
    assert len(body) <= 4096
    value = json.loads(body)
    assert set(value) == {'object_id', 'initialized', 'empty_sql', 'empty_native', 'alarm'}
    assert re.fullmatch('[0-9a-f]{64}', value['object_id'])
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
cfp workers secrets bulk --worker us-stocks-p51b-mock-20261113 \
  --secrets '{"MOCK_CONTROL_TOKEN":null,"REPORT_TOKEN":null}'
```

此命令需要用户另批的目标Worker授权，不能在Admin已撤销且未重新授权时执行。若只生成Version未激活，停止并重审激活操作，不加bypass或盲目第三次部署。用户Dashboard删除并Deploy也是远程写入、须另批；记录额外Version/Deployment。unset不是服务端撤销。未初始化时Stop被设计拒绝，不能宣称STOPPED；处置为停止操作、撤销应用Secrets/临时Token、保留空资源。删除云资源另批。

## 停止条件与回传

任何额外权限/账户元数据范围、收费/升级、子域注册、资源差异、SQLite协调失败、名称冲突、hash不符、绑定/ID不符、Secret激活未知或时间不足：立即停止，保存脱敏错误码/请求ID/时间、核对部分创建，撤销可撤销授权并保留现场。撤销不回滚数据；不改其他项目，不扩权，不删除DO或重建。未能确认撤销时如实报告能力可能仍有效。

回传仅cf版本、核对hash、Worker名、脱敏账户引用、活动版本/Deployment/namespace对应关系、实际ID与空状态、错误码/时刻、撤销结果。不要回传任何Token、Secret JSON、Authorization、Profile或shell变量。实际权限、SQLite首创、Secret激活、传播和云端成本仍NOT_VERIFIED。
