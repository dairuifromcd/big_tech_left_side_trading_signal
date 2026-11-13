import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Miniflare,MiniflareOptions} from 'miniflare';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {newLocalPersistence} from '../scripts/local-runtime.ts';
import {writeTestResult} from './test-output.ts';

const NAME='phase51b-synthetic-20261113-v1',TOKEN='LOCAL_ONLY_CONTROL_CREDENTIAL_00001',INIT='LOCAL_ONLY_INIT_CREDENTIAL_00000001',REPORT='LOCAL_ONLY_REPORT_CREDENTIAL_00001';
test('remote entry in local workerd: private bridge, H01, Alarm, kill and persistence',async t=> {
  const path=newLocalPersistence();let outbound=0;
  const now=Date.now(),bindings={REMOTE_MOCK_ENABLED:'EXPLICIT_PHASE51B_MOCK_V1',MOCK_START_UTC:new Date(now-1000).toISOString(),MOCK_END_UTC:new Date(now+600000).toISOString(),MOCK_INIT_END_UTC:new Date(now+300000).toISOString(),MOCK_CONTROL_TOKEN:TOKEN,MOCK_INIT_TOKEN:INIT,REPORT_TOKEN:REPORT};
  function options(values:Record<string,string>):MiniflareOptions {
    return {host:'127.0.0.1',port:0,cf:false,telemetry:{enabled:false},enableDevRegistry:false,resourcePersistencePath:path,resourceTmpPath:resolve('.tmp'),workers:[{config:{name:'remote-mock-local',compatibilityDate:'2026-11-10',compatibilityFlags:['nodejs_compat'],manifest:{mainModule:'remote-worker.js',modulesRoot:resolve('dist'),modules:{'remote-worker.js':{type:'esm',contents:readFileSync(resolve('dist/remote-worker.js'),'utf8')}}},exports:{RemoteMockCoordinator:{type:'durable-object',storage:'sqlite'}},env:{COORDINATOR:{type:'durable-object',worker:'remote-mock-local',exportName:'RemoteMockCoordinator'},...Object.fromEntries(Object.entries(values).map(([key,value])=>[key,{type:'text' as const,value}]))}},dev:{outboundService:{type:'fetcher',handler:()=>{outbound++;throw Error('EXTERNAL_NETWORK_FORBIDDEN');}}}}]};
  }
  let mf=new Miniflare(options({}));
  try {
    await mf.ready;let ns=await mf.getDurableObjectNamespace('COORDINATOR');const id=ns.idFromName(NAME).toString();let stub:any=ns.getByName(NAME);
    const command={operation:'INITIALIZE_EMPTY_ISOLATED_MOCK',target_object_id:id,request_id:'local-runtime-init',operator:'LOCAL_WORKERD',authorization_reference:'LOCAL_ONLY',reason:'Gate A local runtime verification'};
    await t.test('default remote config refuses management and report',async()=> {
      assert.equal((await mf.dispatchFetch('https://mock.invalid/_mock/status')).status,403);await assert.rejects(()=>stub.initializeIsolatedMock(command,INIT));
    });
    await mf.setOptions(options({...bindings,MOCK_INIT_ENABLED:'EXPLICIT_ISOLATED_MOCK_V1',MOCK_INIT_OBJECT_ID:id}));
    ns=await mf.getDurableObjectNamespace('COORDINATOR');stub=ns.getByName(NAME);
    await t.test('identity read-only and exact credential/target required',async()=> {
      const before=await stub.identity(TOKEN);assert.equal(before.empty_sql,true);assert.equal(before.empty_native,true);assert.equal(before.alarm,null);
      await assert.rejects(()=>stub.initializeIsolatedMock(command,REPORT));
      await assert.rejects(()=>stub.initializeIsolatedMock({...command,target_object_id:'wrong-object'},INIT));
      assert.equal((await stub.identity(TOKEN)).empty_sql,true);
    });
    await t.test('explicit initialization once, no LOCAL_TESTING or arbitrary SQL RPC',async()=> {
      const receipt=await stub.initializeIsolatedMock(command,INIT);assert.ok(receipt.receipt_id);await assert.rejects(()=>stub.initializeIsolatedMock(command,INIT));
      await assert.rejects(async()=>{await stub.testQuery('DELETE FROM states');});
    });
    await t.test('HTTP bridge enforces separate credentials and strict commands',async()=> {
      const fetch=(p:string,method='GET',token?:string,body?:any)=>mf.dispatchFetch('https://mock.invalid'+p,{method,headers:token?{Authorization:'Bearer '+token}:{},...(body?{body:JSON.stringify(body)}:{})});
      assert.equal((await fetch('/api/overview')).status,401);assert.equal((await fetch('/_mock/start','POST',REPORT,{fixture_date:'2026-11-06'})).status,403);
      assert.equal((await fetch('/_mock/start','POST',TOKEN,{fixture_date:'2026-11-06',sql:'DROP TABLE states'})).status,403);
      assert.equal((await fetch('/_mock/start','POST',TOKEN,{fixture_date:'2026-11-12'})).status,403);
      assert.equal((await fetch('/api/overview','POST',REPORT,{})).status,405);
      assert.equal((await fetch('/_mock/stop','POST',TOKEN,{extra:true})).status,403);
      assert.equal((await fetch('/_mock/start','POST',TOKEN,{fixture_date:'x'.repeat(5000)})).status,413);
      assert.equal((await mf.dispatchFetch('https://mock.invalid/_mock/status',{headers:{Authorization:TOKEN}})).status,403);
    });
    await t.test('Alarm commits synthetic state, duplicate start is idempotent',async()=> {
      assert.equal(await stub.startFixture('2026-11-06',TOKEN),'STARTED');assert.equal(await stub.startFixture('2026-11-06',TOKEN),'DUPLICATE');
      // alarm is a reserved RPC method. Observe actual local platform delivery.
      let status=await stub.status(TOKEN);
      for(let i=0;i<30&&status.experiment.collectors===0;i++){await new Promise(r=>setTimeout(r,100));status=await stub.status(TOKEN);}
      assert.equal(status.experiment.collectors,1);assert.equal(status.claims.filter((c:any)=>c.status==='COMMITTED').length,1);
      await stub.startFixture('2026-11-06',TOKEN);status=await stub.status(TOKEN);assert.equal(status.experiment.collectors,1);
    });
    await t.test('six read-only reports have explicit synthetic provenance',async()=> {
      const before=await stub.status(TOKEN);
      for(const p of ['/api/overview','/api/runs/latest','/api/health','/api/events','/api/assets/NVDA','/api/assets/NVDA/history']) {
        const r=await mf.dispatchFetch('https://mock.invalid'+p,{headers:{Authorization:'Bearer '+REPORT}});assert.equal(r.status,200);const body:any=await r.json();assert.equal(body.mode,'DRY_RUN_REMOTE_MOCK_ONLY');assert.equal(body.provenance,'SYNTHETIC_NOT_HISTORICAL_PIT');
      }
      const after=await stub.status(TOKEN);assert.deepEqual(after.experiment,before.experiment);assert.deepEqual(after.claims,before.claims);
    });
    await t.test('authenticated stop cancels Alarm and cannot resume',async()=> {
      await stub.stopExperiment(TOKEN);assert.equal((await stub.status(TOKEN)).alarm,null);await new Promise(r=>setTimeout(r,100));assert.equal((await stub.status(TOKEN)).experiment.collectors,1);await assert.rejects(()=>stub.startFixture('2026-11-09',TOKEN));
    });
    await t.test('new runtime reads persisted stop and receipt without an Alarm',async()=> {
      await mf.dispose();mf=new Miniflare(options({...bindings,MOCK_INIT_ENABLED:'EXPLICIT_ISOLATED_MOCK_V1',MOCK_INIT_OBJECT_ID:id}));await mf.ready;
      stub=(await mf.getDurableObjectNamespace('COORDINATOR')).getByName(NAME);const state=await stub.status(TOKEN);assert.equal(state.experiment.status,'STOPPED');assert.equal(state.alarm,null);assert.equal(state.experiment.collectors,1);assert.equal(state.receipt.request_id,command.request_id);
    });
    await t.test('expired initialization is rejected without LOCAL_TESTING',async()=> {
      await mf.setOptions(options({...bindings,MOCK_INIT_ENABLED:'EXPLICIT_ISOLATED_MOCK_V1',MOCK_INIT_OBJECT_ID:id,MOCK_INIT_END_UTC:new Date(now-1).toISOString()}));
      stub=(await mf.getDurableObjectNamespace('COORDINATOR')).getByName(NAME);await assert.rejects(()=>stub.initializeIsolatedMock(command,INIT));
    });
    assert.equal(outbound,0);writeTestResult('remote_mock_workerd_results.json',{environment:'LOCAL_WORKERD_ONLY',checks:9,collector_calls:1,outbound_requests:outbound,kill_alarm_cancelled:true,persisted_stop:true,remote_init_security:'LOCAL_PASS',cloud_initialization:'NOT_VERIFIED',actual_cloud_eviction:'NOT_VERIFIED'});
  }finally{await mf.dispose();}
});
