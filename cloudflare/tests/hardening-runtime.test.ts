import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Miniflare} from 'miniflare';
import {randomBytes,randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {localRuntimeOptions,newLocalPersistence,makeLocalInitializationHarness} from '../scripts/local-runtime.ts';
import {copyFixture,DATE,TIME,NEXT,NEXT_TIME} from './hardening-fixture.ts';
import {canonical,digest} from '../src/storage.ts';
import {writeTestResult} from './test-output.ts';

const credential=randomBytes(32).toString('hex');let outbound=0;
const command=(id:string)=>({operation:'INITIALIZE_EMPTY_ISOLATED_MOCK',target_object_id:id,request_id:randomUUID(),operator:'LOCAL_RUNTIME_TEST',authorization_reference:'PHASE51A_OFFLINE_AUTHORIZATION',reason:'Isolated initialization security test'});
const network=()=>{outbound++;};
test('H01 workerd default policy denies init, monitoring and test backdoor; HTTP has no admin route',async()=> {
  const mf=new Miniflare(localRuntimeOptions(newLocalPersistence(),{},false,network));
  try {
    await mf.ready;const ns=await mf.getDurableObjectNamespace('COORDINATOR'),id=ns.idFromName('fixed-us-stocks-poc-v1').toString(),stub:any=ns.getByName('fixed-us-stocks-poc-v1');
    await assert.rejects(()=>stub.initializeIsolatedMock(command(id),credential));await assert.rejects(()=>stub.testInit());await assert.rejects(()=>stub.testQuery('SELECT 1'));await assert.rejects(()=>stub.testTick(DATE,TIME));await assert.rejects(()=>stub.start(DATE,TIME));
    for(const method of ['GET','POST','PUT']) {
      const r=await mf.dispatchFetch('http://local/api/admin/initialize',{method,headers:{Authorization:'Bearer LOCAL_REPORT_FIXTURE_ONLY'}});assert.ok([404,405,503].includes(r.status));await r.text();
    }
    const report=await mf.dispatchFetch('http://local/api/overview',{headers:{Authorization:'Bearer LOCAL_REPORT_FIXTURE_ONLY'}});assert.equal(report.status,503);await report.text();
    await assert.rejects(()=>stub.start(DATE,TIME));assert.equal(await stub.mockCollectionCount(),0);assert.equal(outbound,0);
  }finally{await mf.dispose();}
});

test('H01 workerd controlled initialization works without LOCAL_TESTING and rejects bad credential/target/replay',async()=> {
  const {mf,stub,objectId}=await makeLocalInitializationHarness(credential,network);
  try {
    await assert.rejects(()=>stub.initializeIsolatedMock(command(objectId),'bad-credential'));
    await assert.rejects(()=>stub.initializeIsolatedMock(command('wrong-object'),credential));
    assert.equal(await stub.mockCollectionCount(),0);assert.equal(outbound,0);
    const receipt=await stub.initializeIsolatedMock(command(objectId),credential);assert.ok(receipt.receipt_id);
    const report=()=>mf.dispatchFetch('http://local/api/overview',{headers:{Authorization:'Bearer LOCAL_REPORT_FIXTURE_ONLY'}});
    const before=await (await report()).text();
    await assert.rejects(()=>stub.initializeIsolatedMock(command(objectId),credential));assert.equal(await (await report()).text(),before);
    await assert.rejects(()=>stub.testInit());
    assert.equal(await stub.start(DATE,TIME),'STARTED');
    let committed=0;
    for(let attempt=0;attempt<40;attempt++) {
      const response=await report(),body=await response.json() as any;
      committed=body.data.filter((asset:any)=>asset.trading_date).length;if(committed)break;await new Promise(r=>setTimeout(r,100));
    }
    assert.equal(committed,1);assert.equal(await stub.mockCollectionCount(),1);
    const healthy=await (await report()).text();await assert.rejects(()=>stub.initializeIsolatedMock(command(objectId),credential));assert.equal(await (await report()).text(),healthy);assert.equal(outbound,0);
  }finally{await mf.dispose();}
});

test('H01 workerd initialization transaction rolls back schema and receipt on injected failure',async()=> {
  const mf=new Miniflare(localRuntimeOptions(newLocalPersistence(),{},true,network));
  try {
    await mf.ready;const ns=await mf.getDurableObjectNamespace('COORDINATOR');
    for(const fault of ['after_schema','after_receipt']) {
      const stub:any=ns.getByName('torn-init-'+fault);
      const before=JSON.stringify(await stub.testQuery("SELECT name,sql FROM sqlite_master WHERE name NOT GLOB '_cf_*'"));
      await assert.rejects(()=>stub.testInit(fault));assert.equal(JSON.stringify(await stub.testQuery("SELECT name,sql FROM sqlite_master WHERE name NOT GLOB '_cf_*'")),before);
      await assert.rejects(()=>stub.testStart(DATE,TIME));assert.equal((await stub.testCalls()).length,0);
      await stub.testInit();await stub.testStart(DATE,TIME);assert.equal(await stub.testTick(DATE,TIME),'COMMITTED');
    }
    assert.equal(outbound,0);
  }finally{await mf.dispose();}
});

test('H02 workerd corrupted checkpoints block every collector before request, including after preflight',async()=> {
  const source=await copyFixture();
  const data=Object.fromEntries(['states','events','runs','claims','evidence','history'].map(table=>[table,source.store.q(`SELECT * FROM ${table}`)]));const ids=source.ids;source.db.close();
  const mf=new Miniflare(localRuntimeOptions(newLocalPersistence(),{},true,network));let blocked=0;
  try {
    await mf.ready;const ns=await mf.getDurableObjectNamespace('COORDINATOR');
    const seed=async(stub:any)=> {
      await stub.testInit();
      for(const [table,rows] of Object.entries(data))for(const row of rows) {
        const values=Object.values(row);await stub.testQuery(`INSERT INTO ${table} VALUES (${values.map(()=>'?').join(',')})`,...values);
      }
    };
    const eventMutation=async(stub:any,id:string,change:(e:any)=>void)=> {
      const row=(await stub.testQuery('SELECT * FROM events WHERE id=?',id))[0],event=JSON.parse(row.body);change(event);const body=canonical(event);await stub.testQuery('UPDATE events SET body=?,hash=? WHERE id=?',body,digest(body),id);
    };
    const stateMutation=async(stub:any,change:(d:any)=>void)=> {
      const row=(await stub.testQuery("SELECT * FROM states WHERE symbol='NVDA'"))[0],doc=JSON.parse(row.body);change(doc);const body=canonical(doc);await stub.testQuery("UPDATE states SET body=?,hash=? WHERE symbol='NVDA'",body,digest(`${row.version}:${body}`));
    };
    const scenarios:[string,(stub:any)=>Promise<any>][]=[
      ['event hash',s=>s.testQuery("UPDATE events SET hash='broken' WHERE id=?",ids.NVDA.pending)],
      ['semantic ID',s=>s.testQuery('UPDATE events SET id=? WHERE id=?','0'.repeat(64),ids.NVDA.pending)],
      ['evidence hash',s=>eventMutation(s,ids.NVDA.pending,e=>{e.evidence_versions[0].evidence.fixture='corrupt';})],
      ['missing audit',s=>eventMutation(s,ids.NVDA.pending,e=>{e.audit_trail=[];})],
      ['audit final state',s=>eventMutation(s,ids.NVDA.pending,e=>{e.audit_trail[0].to_status='CONFIRMED';})],
      ['confirmed reference',s=>s.testQuery('DELETE FROM events WHERE id=?',ids.NVDA.confirmed)],
      ['pending missing',s=>stateMutation(s,d=>{d.threshold_state.pending_event_ids=['missing'];})],
      ['pending wrong status',s=>stateMutation(s,d=>{d.threshold_state.pending_event_ids=[ids.NVDA.confirmed,ids.NVDA.revision].sort();})],
      ['revision reference',s=>stateMutation(s,d=>{d.revision_review_event_ids=[];})],
      ['category',s=>s.testQuery("UPDATE events SET category='indices' WHERE id=?",ids.NVDA.pending)],
      ['duplicate evidence',s=>eventMutation(s,ids.NVDA.pending,e=>{e.evidence_versions.push(e.evidence_versions[0]);})],
      ['unknown hash scheme',s=>eventMutation(s,ids.NVDA.pending,e=>{delete e.evidence_versions[0].hash_scheme;})],
      ['dependency flags',s=>eventMutation(s,ids.NVDA.confirmed,e=>{delete e.dependency_review_event_ids;delete e.dependency_review_required;})]
    ];
    for(let index=0;index<scenarios.length;index++) {
      const [name,mutate]=scenarios[index],stub:any=ns.getByName('corruption-'+index);await seed(stub);await mutate(stub);
      const before=JSON.stringify(await stub.testQuery('SELECT * FROM states'))+JSON.stringify(await stub.testQuery('SELECT * FROM events'))+JSON.stringify(await stub.testQuery('SELECT * FROM claims'));
      await assert.rejects(()=>stub.testStart(NEXT,NEXT_TIME),()=>true,name);assert.equal((await stub.testCalls()).length,0,name);assert.equal(outbound,0,name);
      assert.equal(JSON.stringify(await stub.testQuery('SELECT * FROM states'))+JSON.stringify(await stub.testQuery('SELECT * FROM events'))+JSON.stringify(await stub.testQuery('SELECT * FROM claims')),before,name);blocked++;
    }
    const dirty:any=ns.getByName('changed-after-start');await seed(dirty);await dirty.testStart(NEXT,NEXT_TIME);await dirty.testQuery("UPDATE events SET hash='corrupt' WHERE id=?",ids.NVDA.pending);await assert.rejects(()=>dirty.testTick(NEXT,NEXT_TIME));assert.equal((await dirty.testCalls()).length,0);assert.equal(outbound,0);blocked++;
    const legacy:any=ns.getByName('legacy-seven');await legacy.testInit();const pending=JSON.parse(readFileSync(new URL('../fixtures/legacy-pending.json',import.meta.url),'utf8'));
    for(const [id,event] of Object.entries(pending)){const body=canonical(event);await legacy.testQuery('INSERT INTO events VALUES (?,?,?,?)','stocks',id,body,digest(body));}
    const before=JSON.stringify(await legacy.testQuery('SELECT * FROM events'));await assert.rejects(()=>legacy.testStart(NEXT,NEXT_TIME));assert.equal((await legacy.testCalls()).length,0);assert.equal(JSON.stringify(await legacy.testQuery('SELECT * FROM events')),before);assert.equal(outbound,0);blocked++;
  }finally{await mf.dispose();}
  writeTestResult('hardening_runtime_results.json',{status:'PASS',platform:'LOCAL_WORKERD_SQLITE',blocked_checkpoint_cases:blocked,collector_calls_for_blocked_cases:0,outbound_requests:outbound,remote_initialization:'NOT_VERIFIED'});
});
