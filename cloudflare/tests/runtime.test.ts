import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync} from 'node:fs';
import {resolve} from 'node:path';
import {Miniflare} from 'miniflare';
const date='2026-11-06',now=Date.parse('2026-11-07T00:00:00Z');
let outbound=0;
const root=mkdtempSync(resolve('.tmp/workerd-'));
function runtime() {
  return new Miniflare({
    host:'127.0.0.1',port:0,cf:false,telemetry:{enabled:false},enableDevRegistry:false,
    resourcePersistencePath:root,resourceTmpPath:resolve('.tmp'),
    unsafeTriggerHandlers:true,
    workers:[{config:{
      name:'poc',compatibilityDate:'2026-11-10',compatibilityFlags:['nodejs_compat'],
      manifest:{mainModule:'worker.js',modulesRoot:resolve('dist'),modules:{'worker.js':{type:'esm',contents:readFileSync(resolve('dist/worker.js'),'utf8')}}},
      exports:{ExecutionCoordinator:{type:'durable-object',storage:'sqlite'}},
      env:{COORDINATOR:{type:'durable-object',worker:'poc',exportName:'ExecutionCoordinator'},REPORT_TOKEN:{type:'text',value:'local-fixture-credential'},LOCAL_TESTING:{type:'text',value:'1'}}
    },dev:{outboundService:{type:'fetcher',handler:()=>{outbound++;throw Error('EXTERNAL_NETWORK_FORBIDDEN');}}}}]
  });
}
async function finish(stub:any) {for(let i=0;i<20;i++){const s=await stub.testTick(date,now+i*35000);if(s==='COMPLETE')return;}throw Error('Incomplete run');}
test('workerd SQLite: 12 assets, duplicate schedulers, API purity, runtime restart, uncertain claims and atomic rollback',async()=> {
  const cpu=process.cpuUsage(),memory=process.memoryUsage();let mf=runtime();
  const observations:any={};
  try {
    await mf.ready;
    const ns=await mf.getDurableObjectNamespace('COORDINATOR');const stub:any=ns.getByName('fixed-us-stocks-poc-v1');
    await stub.testInit();
    assert.deepEqual(await Promise.all([stub.testStart(date,now),stub.testStart(date,now)]),['STARTED','DUPLICATE']);
    await finish(stub);assert.equal((await stub.testQuery('SELECT * FROM states')).length,12);assert.equal((await stub.testCalls()).length,12);
    assert.equal(await stub.testTick(date,now+1e6),'COMPLETE');assert.equal((await stub.testCalls()).length,12);
    assert.equal((await mf.dispatchFetch('http://local/api/overview')).status,401);
    const auth={Authorization:'Bearer local-fixture-credential'};
    assert.equal((await mf.dispatchFetch('http://local/api/events',{method:'POST',headers:auth})).status,405);
    const snapshot=async()=>JSON.stringify(await stub.testQuery('SELECT * FROM states'))+JSON.stringify(await stub.testQuery('SELECT * FROM claims'))+JSON.stringify(await stub.testQuery('SELECT * FROM events'));
    const before=await snapshot();
    for(const route of ['/api/overview','/api/assets/%5ESOX','/api/assets/NVDA/history?limit=1','/api/events','/api/runs/latest','/api/health']){
      const r=await mf.dispatchFetch('http://local'+route,{headers:auth});assert.equal(r.status,200,await r.clone().text());const body=await r.json() as any;assert.equal(body.schema_version,'report-v1');
    }
    assert.equal(await snapshot(),before);
    const trigger=await mf.dispatchFetch(`http://local/cdn-cgi/local/scheduled?time=${now}&cron=0+0+*+*+TUE-SAT`);
    assert.equal(trigger.status,200,await trigger.clone().text());await trigger.text();assert.equal((await stub.testCalls()).length,12);
    const alarmStub:any=ns.getByName('platform-alarm');await alarmStub.testInit();await alarmStub.testStart(date,now);await alarmStub.testArm(10);
    for(let attempt=0;attempt<30&&(await alarmStub.testCalls()).length===0;attempt++)await new Promise(r=>setTimeout(r,100));
    assert.equal((await alarmStub.testCalls()).length,1);await alarmStub.testArm(10);await new Promise(r=>setTimeout(r,200));
    assert.equal((await alarmStub.testCalls()).length,1);await alarmStub.testCancel();
    observations.local_scheduled_handler=true;observations.platform_alarm_delivery=true;observations.duplicate_alarm_did_not_collect=true;
    observations.metrics=JSON.parse(JSON.stringify(await stub.testMetrics()));
    observations.calls=JSON.parse(JSON.stringify(await stub.testCalls()));observations.api_readonly=true;
    // Faults are tested in separate DO identities, then inspected after new RPCs.
    for(const fault of ['before_request','after_request','raw_write','state_write','event_write']) {
      const s:any=ns.getByName('fault-'+fault);await s.testInit();await s.testStart(date,now);await assert.rejects(()=>s.testTick(date,now,fault));
      const calls=(await s.testCalls()).length;assert.equal((await s.testQuery('SELECT * FROM states')).length,0);
      const status=await s.testTick(date,now+35000);assert.equal(status,['state_write','event_write'].includes(fault)?'COMMITTED':'UNCERTAIN_EXECUTION');assert.equal((await s.testCalls()).length,calls);
    }
    const unknown:any=ns.getByName('new-uninitialized');const unavailable=await unknown.report(new Request('http://local/api/health'));assert.equal(unavailable.status,503);await unavailable.text();
    await stub.testBackup('selected-checkpoint');await stub.testQuery("DELETE FROM states WHERE symbol='NVDA'");
    // Node SQLite tests assert the exact STATE_ERROR. Miniflare v5's RPC bridge
    // currently wraps some synchronous transaction errors as AssertionError.
    await assert.rejects(()=>stub.testStart('2026-11-09',Date.parse('2026-11-10T00:00:00Z')));
    assert.equal((await stub.testQuery("SELECT * FROM runs WHERE date='2026-11-09'")).length,0);
    assert.equal((await stub.testCalls()).length,12);
    await stub.testRestore('selected-checkpoint');
    const checkpoint=await snapshot();
    await mf.dispose();mf=runtime();await mf.ready;
    const reopened:any=(await mf.getDurableObjectNamespace('COORDINATOR')).getByName('fixed-us-stocks-poc-v1');
    assert.equal(JSON.stringify(await reopened.testQuery('SELECT * FROM states'))+JSON.stringify(await reopened.testQuery('SELECT * FROM claims'))+JSON.stringify(await reopened.testQuery('SELECT * FROM events')),checkpoint);
    assert.equal(await reopened.testStart(date,now),'DUPLICATE');assert.equal((await reopened.testCalls()).length,0);
    observations.restart_persistence=true;observations.backup_restore=true;
    const unknownClaim:any=(await mf.getDurableObjectNamespace('COORDINATOR')).getByName('restart-unknown');await unknownClaim.testInit();await unknownClaim.testStart(date,now);await assert.rejects(()=>unknownClaim.testTick(date,now,'before_request'));
    await mf.dispose();mf=runtime();await mf.ready;
    const recovered:any=(await mf.getDurableObjectNamespace('COORDINATOR')).getByName('restart-unknown');assert.equal(await recovered.testTick(date,now+35000),'UNCERTAIN_EXECUTION');assert.equal((await recovered.testCalls()).length,0);
    observations.uncertain_after_restart=true;assert.equal(outbound,0);
  } finally {await mf.dispose();}
  writeFileSync('../phase5_1_cloudflare_free/runtime_results.json',JSON.stringify({status:'PASS',platform:'LOCAL_MINIFLARE_WORKERD_SQLITE',...observations,outbound_requests:outbound,cpu_host_process_microseconds:process.cpuUsage(cpu),memory_host_before:memory,memory_host_after:process.memoryUsage(),real_cloudflare_cpu:'NOT_VERIFIED',real_cloudflare_memory:'NOT_VERIFIED'},null,2)+'\n');
});
