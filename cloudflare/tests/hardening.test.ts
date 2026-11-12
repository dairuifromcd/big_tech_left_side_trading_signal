import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {Store,canonical,digest} from '../src/storage.ts';
import {Coordinator} from '../src/coordinator.ts';
import {MockYahoo} from '../src/mock.ts';
import {authorizeInitialization,localTestReceipt,makeReceipt} from '../src/initialization.ts';
import {api} from '../src/api.ts';
import {connection,copyFixture,replaceState,replaceEvent,snapshot,nextCollector,finish,DATE,TIME,NEXT,NEXT_TIME} from './hardening-fixture.ts';

test('H01 explicit empty initialization writes a verifiable one-time receipt',()=> {
  const {db,store}=connection(),receipt=localTestReceipt();store.initialize(receipt);store.guard();
  const stored=store.q("SELECT value FROM meta WHERE key='receipt'")[0].value;assert.equal(stored,canonical(receipt));assert.equal(store.q('SELECT * FROM initialization_audit')[0].hash,digest(stored));
  const before=snapshot(store);assert.throws(()=>store.initialize(),/REFUSED/);assert.equal(snapshot(store),before);db.close();
});
test('H01 uninitialized monitor and read API fail safely without writes or collector',async()=> {
  const {db,store}=connection(),mock=new MockYahoo(),runner=new Coordinator(store,mock);
  assert.throws(()=>runner.start(DATE,TIME),/STATE_ERROR/);assert.equal(api(store,new Request('http://local/api/health')).status,503);assert.equal(mock.calls.length,0);assert.equal(store.q('SELECT * FROM sqlite_master').length,0);db.close();
});
for(const table of ['states','events','claims','evidence','history','backups','audit','empty_old_table','__miniflare_do_name','_cf_forgotten_prices'])test('H01 refuses storage remnant '+table,()=> {
  const {db,store}=connection();store.q(`CREATE TABLE ${table} (body TEXT)`);if(table!=='empty_old_table')store.q(`INSERT INTO ${table} VALUES ('preserve-me')`);
  const before=snapshot(store);assert.throws(()=>store.initialize(),/REFUSED/);assert.equal(snapshot(store),before);db.close();
});
for(const fault of ['after_schema','after_receipt'] as const)test('H01 initialization failure is fully atomic '+fault,()=> {
  const {db,store}=connection();assert.throws(()=>store.initialize(localTestReceipt(),fault),/INJECTED/);assert.equal(store.q('SELECT * FROM sqlite_master').length,0);store.initialize();store.guard();db.close();
});
test('H01 deleted receipt or cleared rows cannot authorize reinitialization over old schema',()=> {
  const {db,store}=connection();store.initialize();store.q("DELETE FROM meta WHERE key='receipt'");const before=snapshot(store);assert.throws(()=>store.initialize(),/REFUSED/);assert.equal(snapshot(store),before);assert.throws(()=>store.guard(),/STATE_ERROR/);db.close();
});
test('H01 authorization requires enabled policy, separate secret and exact DO target',()=> {
  const {db,store}=connection(),receipt=localTestReceipt(),secret='local-only-management-credential-0123456789';
  const command={operation:receipt.operation,target_object_id:receipt.target_object_id,request_id:receipt.request_id,operator:receipt.operator,authorization_reference:receipt.authorization_reference,reason:receipt.reason};
  const policy={MOCK_INIT_ENABLED:'EXPLICIT_ISOLATED_MOCK_V1',MOCK_INIT_TOKEN:secret,MOCK_INIT_OBJECT_ID:receipt.target_object_id};
  for(const attempt of [()=>authorizeInitialization({},receipt.target_object_id,command,secret),()=>authorizeInitialization(policy,receipt.target_object_id,command,'bad'),()=>authorizeInitialization(policy,'wrong-object',command,secret)])assert.throws(attempt,/INITIALIZATION_/);
  assert.equal(store.q('SELECT * FROM sqlite_master').length,0);authorizeInitialization(policy,receipt.target_object_id,command,secret);store.initialize(receipt);assert.ok(!store.q("SELECT value FROM meta WHERE key='receipt'")[0].value.includes(secret));db.close();
});
test('H01 command rejects extra credential fields before building a receipt',()=> {
  const receipt=localTestReceipt();
  const command={operation:receipt.operation,target_object_id:receipt.target_object_id,request_id:receipt.request_id,operator:receipt.operator,authorization_reference:receipt.authorization_reference,reason:receipt.reason};
  assert.doesNotThrow(()=>makeReceipt(command));
  assert.throws(()=>makeReceipt({...command,credential:'must-not-enter-audit'} as any),/COMMAND_INVALID/);
});
test('H01 receipt corruption fails closed and does not restore or reset it',()=> {
  const {db,store}=connection();store.initialize();store.q("UPDATE meta SET value='{}' WHERE key='receipt'");const before=snapshot(store);assert.throws(()=>store.guard(),/STATE_ERROR/);assert.equal(snapshot(store),before);db.close();
});
test('H02 valid full checkpoint validation is read-only and supports next-day mock execution',async()=> {
  const {db,store}=await copyFixture(),before=snapshot(store);const proof=store.validateFullCheckpoint();assert.equal(proof.state_count,12);assert.equal(proof.event_count,8);assert.equal(snapshot(store),before);
  const collector=nextCollector(),runner=new Coordinator(store,collector);runner.start(NEXT,NEXT_TIME);await finish(runner,NEXT,NEXT_TIME);assert.equal(collector.calls.length,12);db.close();
});
const mutations:{name:string;apply:(store:Store,ids:any)=>void}[]=[
  {name:'state body hash',apply:s=>s.q("UPDATE states SET body='{}' WHERE symbol='NVDA'")},
  {name:'state schema',apply:s=>replaceState(s,'NVDA',d=>{d.checkpoint_schema_version=99;})},
  {name:'database schema',apply:s=>s.q("UPDATE meta SET value='99' WHERE key='schema'")},
  {name:'state event model',apply:s=>replaceState(s,'NVDA',d=>{d.event_model_version='indices-revision-market-v2';})},
  {name:'state version',apply:s=>s.q("UPDATE states SET version=0 WHERE symbol='NVDA'")},
  {name:'stock identity',apply:s=>replaceState(s,'NVDA',d=>{d.identity_snapshot.currency='EUR';})},
  {name:'index identity',apply:s=>replaceState(s,'^GSPC',d=>{d.identity_snapshot.instrumentType='EQUITY';})},
  {name:'history Close mismatch',apply:s=>replaceState(s,'NVDA',d=>{delete d.history_closes[Object.keys(d.history_closes)[0]];})},
  {name:'metrics recomputed hash but invalid value',apply:s=>replaceState(s,'NVDA',d=>{d.drawdown=-0.99;})},
  {name:'threshold alias',apply:s=>replaceState(s,'NVDA',d=>{d.triggered_thresholds=[];})},
  {name:'event body hash with valid state',apply:(s,i)=>s.q("UPDATE events SET body='{}' WHERE id=?",i.NVDA.pending)},
  {name:'event ID primary key',apply:(s,i)=>s.q('UPDATE events SET id=? WHERE id=?','a'.repeat(64),i.NVDA.pending)},
  {name:'semantic event threshold',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{e.threshold=10;})},
  {name:'evidence version hash',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{e.evidence_versions[0].evidence.fixture='corrupt';})},
  {name:'missing evidence versions',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{e.evidence_versions=[];})},
  {name:'duplicate evidence versions',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{e.evidence_versions.push(e.evidence_versions[0]);})},
  {name:'missing audit trail',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{delete e.audit_trail;})},
  {name:'audit final status',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{e.audit_trail[0].to_status='CONFIRMED';})},
  {name:'audit chain rewrite',apply:(s,i)=>replaceEvent(s,i.NVDA.revision,e=>{e.audit_trail[1].from_status='REJECTED';})},
  {name:'confirmed threshold missing event',apply:(s,i)=>s.q('DELETE FROM events WHERE id=?',i.NVDA.confirmed)},
  {name:'pending missing reference',apply:s=>replaceState(s,'NVDA',d=>{d.threshold_state.pending_event_ids.push('z'.repeat(64));d.threshold_state.pending_event_ids.sort();})},
  {name:'pending points to confirmed event',apply:(s,i)=>replaceState(s,'NVDA',d=>{d.threshold_state.pending_event_ids=[i.NVDA.confirmed,i.NVDA.revision].sort();})},
  {name:'revision review mismatch',apply:s=>replaceState(s,'NVDA',d=>{d.revision_review_event_ids=[];})},
  {name:'missing pending reference silently dropped',apply:s=>replaceState(s,'NVDA',d=>{d.threshold_state.pending_event_ids=[];})},
  {name:'stock in index category',apply:(s,i)=>s.q("UPDATE events SET category='indices' WHERE id=?",i.NVDA.pending)},
  {name:'index in stock category',apply:(s,i)=>s.q("UPDATE events SET category='stocks' WHERE id=?",i['^GSPC'].pending)},
  {name:'wrong event symbol',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{e.symbol='AAPL';})},
  {name:'wrong event model',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{e.event_model_version='indices-revision-market-v2';})},
  {name:'invalid event status',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{e.status='DELIVERED';})},
  {name:'conflicting duplicate event across category',apply:(s,i)=>{const r=s.q('SELECT * FROM events WHERE id=?',i.NVDA.pending)[0];s.q('INSERT INTO events VALUES (?,?,?,?)','indices',r.id,r.body,r.hash);}},
  {name:'dependency flags silently removed',apply:(s,i)=>replaceEvent(s,i.NVDA.confirmed,e=>{delete e.dependency_review_event_ids;delete e.dependency_review_required;})},
  {name:'dependency points to wrong symbol',apply:(s,i)=>replaceEvent(s,i.NVDA.confirmed,e=>{e.dependency_review_event_ids=[i['^GSPC'].revision];e.audit_trail.at(-1).revision_event_id=i['^GSPC'].revision;})},
  {name:'unknown legacy evidence scheme',apply:(s,i)=>replaceEvent(s,i.NVDA.pending,e=>{delete e.evidence_versions[0].hash_scheme;})},
  {name:'missing committed state',apply:s=>s.q("DELETE FROM states WHERE symbol='AVGO'")},
  {name:'raw evidence hash',apply:s=>s.q("UPDATE evidence SET raw='{}' WHERE key=?",DATE+'/NVDA')},
  {name:'history DTO hash',apply:s=>s.q("UPDATE history SET body='{}' WHERE symbol='NVDA'")},
  {name:'trigger protection removed',apply:s=>s.q('DROP TRIGGER checkpoint_events_update')}
  ,{name:'unexpected trigger',apply:s=>s.q('CREATE TRIGGER bypass AFTER UPDATE ON events BEGIN UPDATE checkpoint_control SET generation=validated_generation WHERE id=1; END')}
];
for(const mutation of mutations)test('H02 blocks before collector: '+mutation.name,async()=> {
  const {db,store,ids}=await copyFixture();mutation.apply(store,ids);const before=snapshot(store),collector=nextCollector(),runner=new Coordinator(store,collector);
  assert.throws(()=>runner.start(NEXT,NEXT_TIME),/STATE_ERROR/);assert.equal(collector.calls.length,0);assert.equal(snapshot(store),before);assert.throws(()=>store.initialize(),/REFUSED/);assert.equal(snapshot(store),before);db.close();
});
test('H02 repair of isolated copy restores valid preflight, without resetting pending or rejected events',async()=> {
  const {db,store,ids}=await copyFixture(),original=store.q('SELECT * FROM events WHERE id=?',ids.NVDA.pending)[0];
  store.q("UPDATE events SET hash='broken' WHERE id=?",original.id);const collector=nextCollector(),runner=new Coordinator(store,collector);assert.throws(()=>runner.start(NEXT,NEXT_TIME),/STATE_ERROR/);assert.equal(collector.calls.length,0);
  store.q('UPDATE events SET body=?,hash=? WHERE id=?',original.body,original.hash,original.id);store.validateFullCheckpoint();runner.start(NEXT,NEXT_TIME);assert.equal(await runner.tick(NEXT,NEXT_TIME),'COMMITTED');assert.equal(collector.calls.length,1);
  assert.equal(store.ledger('NVDA')[ids.NVDA.pending].status,'PENDING_REVIEW');assert.equal(store.ledger('NVDA')[ids.NVDA.rejected].status,'REJECTED');db.close();
});
test('H02 mutation after daily preflight is detected before the first collector call',async()=> {
  const {db,store,ids}=await copyFixture(),collector=nextCollector(),runner=new Coordinator(store,collector);runner.start(NEXT,NEXT_TIME);
  replaceEvent(store,ids.NVDA.pending,e=>{e.evidence_versions[0].evidence.fixture='changed-after-start';});const before=snapshot(store);
  await assert.rejects(()=>runner.tick(NEXT,NEXT_TIME),/STATE_ERROR/);assert.equal(collector.calls.length,0);assert.equal(snapshot(store),before);db.close();
});
test('H02 full scan runs once per new day, not per asset or report read',async()=> {
  const {db,store}=connection();store.initialize();const runner=new Coordinator(store,new MockYahoo());runner.start(DATE,TIME);assert.equal(store.fullValidations,1);await finish(runner);assert.equal(store.fullValidations,1);
  for(let i=0;i<2;i++)assert.equal(api(store,new Request('http://local/api/overview')).status,200);assert.equal(store.fullValidations,1);db.close();
});
test('H02 seven legacy pending remain unchanged in isolated SQL; unsupported hashes explicitly block',()=> {
  const {db,store}=connection();store.initialize();const old=JSON.parse(readFileSync(new URL('../fixtures/legacy-pending.json',import.meta.url),'utf8'));
  for(const [id,event] of Object.entries(old)){const body=canonical(event);store.q('INSERT INTO events VALUES (?,?,?,?)','stocks',id,body,digest(body));}
  const before=snapshot(store),collector=nextCollector(),runner=new Coordinator(store,collector);
  assert.throws(()=>runner.start(NEXT,NEXT_TIME),/LEGACY_EVIDENCE_MIGRATION_REQUIRED/);assert.equal(collector.calls.length,0);assert.equal(Object.keys(old).length,7);assert.deepEqual(store.ledger('NVDA'),old);assert.equal(snapshot(store),before);db.close();
});
for(const change of ['pending promotion','rejected reopening','dependency removal'])test('H02 symbol commit preserves prior decisions: '+change,async()=> {
  const {db,store,ids}=await copyFixture(),beforeStates=canonical(store.q('SELECT * FROM states')),beforeEvents=canonical(store.q('SELECT * FROM events'));
  const original=store.commit.bind(store);store.commit=(key,symbol,version,doc,ledger,fault)=> {
    if(change==='pending promotion') {ledger[ids.NVDA.pending].status='CONFIRMED';ledger[ids.NVDA.pending].audit_trail[0].to_status='CONFIRMED';}
    else if(change==='rejected reopening') {ledger[ids.NVDA.rejected].status='CONFIRMED';ledger[ids.NVDA.rejected].audit_trail[0].to_status='CONFIRMED';}
    else {delete ledger[ids.NVDA.confirmed].dependency_review_event_ids;delete ledger[ids.NVDA.confirmed].dependency_review_required;}
    original(key,symbol,version,doc,ledger,fault);
  };
  const collector=nextCollector(),runner=new Coordinator(store,collector);runner.start(NEXT,NEXT_TIME);assert.equal(await runner.tick(NEXT,NEXT_TIME),'STATE_ERROR');assert.equal(collector.calls.length,1);
  assert.equal(canonical(store.q('SELECT * FROM states')),beforeStates);assert.equal(canonical(store.q('SELECT * FROM events')),beforeEvents);db.close();
});
