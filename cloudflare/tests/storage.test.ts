import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {Store,register,canonical,digest} from '../src/storage.ts';
import {Coordinator} from '../src/coordinator.ts';
import {MockYahoo} from '../src/mock.ts';
import {api} from '../src/api.ts';
import {readFileSync} from 'node:fs';
import {SYMBOLS,stableId,RecordValue as R} from '../src/core.ts';
import {gapPlan,validateArchive} from '../src/recovery.ts';
const target='2026-11-06',start=Date.parse('2026-11-07T00:00:00Z');
export function sqlite(path=':memory:') {
  const db=new DatabaseSync(path);
  const store=new Store({sql:{exec(sql,...args) {
    const stmt=db.prepare(sql);const rows=stmt.all(...args);
    return {toArray:()=>rows};
  }},transactionSync(fn) {db.exec('BEGIN IMMEDIATE');try{const result=fn();db.exec('COMMIT');return result;}catch(e){db.exec('ROLLBACK');throw e;}}});
  return {db,store};
}
const fresh=(mock=new MockYahoo())=>{const {db,store}=sqlite();store.initialize();const engine=new Coordinator(store,mock);return {db,store,mock,engine};};
async function finish(engine:Coordinator,date=target,now=start) {let result='';for(let i=0;i<30;i++){result=await engine.tick(date,now+i*35000);if(result==='COMPLETE')return result;}throw Error('Not complete: '+result);}
test('12 symbols: baseline, duplicate date, independent categories and report baseline semantics',async()=> {
  const {engine,store,mock,db}=fresh();assert.equal(engine.start(target,start),'STARTED');await finish(engine);
  assert.equal(store.q('SELECT * FROM states').length,12);assert.equal(mock.calls.length,12);assert.equal(engine.start(target,start),'DUPLICATE');await engine.tick(target,start+999999);assert.equal(mock.calls.length,12);
  const report=await api(store,new Request('http://local/api/overview')).json() as any;assert.equal(report.data.length,12);
  assert.equal(report.data.find((r:R)=>r.symbol==='^SOX').watch_tier,'WATCH_30');assert.equal(store.q('SELECT * FROM events').length,0);assert.equal(store.q('SELECT DISTINCT category FROM states').length,2);db.close();
});
test('simultaneous schedulers and overlapping dates',async()=> {
  const {engine,db}=fresh();assert.deepEqual(await Promise.all([Promise.resolve().then(()=>engine.start(target,start)),Promise.resolve().then(()=>engine.start(target,start))]),['STARTED','DUPLICATE']);assert.throws(()=>engine.start('2026-11-09',Date.parse('2026-11-10T00:00:00Z')),/OVERLAPPING/);db.close();
});
test('durable global starts >=5sec and batch-boundary >=35sec, duplicate ticks issue no duplicate requests',async()=> {
  const {engine,store,mock,db}=fresh();engine.start(target,start);assert.equal(await engine.tick(target,start),'COMMITTED');assert.equal(await engine.tick(target,start),'WAIT');
  assert.equal(await engine.tick(target,start+4999),'WAIT');await finish(engine,target,start+5000);
  const claims=store.q('SELECT * FROM claims ORDER BY ordinal');for(let i=1;i<claims.length;i++)assert.ok(claims[i].started-claims[i-1].started>=(i%3===0?35000:5000));assert.equal(mock.calls.length,12);db.close();
});
for(const fault of ['before_request','after_request','raw_write'])test('uncertain execution '+fault+' never repeats collection',async()=> {
  const {engine,store,mock,db}=fresh();engine.start(target,start);await assert.rejects(()=>engine.tick(target,start,fault));
  const count=mock.calls.length;assert.equal(await new Coordinator(store,mock).tick(target,start+100000),'UNCERTAIN_EXECUTION');assert.equal(await engine.tick(target,start+200000),'UNCERTAIN_EXECUTION');assert.equal(mock.calls.length,count);assert.equal(store.q('SELECT * FROM states').length,0);db.close();
});
for(const fault of ['state_write','event_write'])test('atomic rollback '+fault+' reprocesses saved raw without network',async()=> {
  const {engine,store,mock,db}=fresh();engine.start(target,start);await assert.rejects(()=>engine.tick(target,start,fault));
  assert.equal(store.q('SELECT * FROM states').length,0);assert.equal(store.q('SELECT * FROM events').length,0);assert.equal(store.q('SELECT * FROM evidence').length,1);assert.equal(mock.calls.length,1);
  assert.equal(await new Coordinator(store,mock).tick(target,start+35000),'COMMITTED');assert.equal(mock.calls.length,1);db.close();
});
test('raw evidence immutable; same input cannot overwrite bytes or origin',()=> {
  const {store,db}=fresh();assert.equal(store.putEvidence('x','abc'),store.putEvidence('x','abc'));assert.throws(()=>store.putEvidence('x','abd'),/IMMUTABLE/);assert.throws(()=>store.putEvidence('x','abc','RECONSTRUCTED'),/IMMUTABLE/);db.close();
});
test('one symbol data failure does not contaminate eleven successful states',async()=> {
  const {engine,store,mock,db}=fresh(new MockYahoo(500,'AAPL'));engine.start(target,start);await finish(engine);assert.equal(mock.calls.length,12);assert.equal(store.q('SELECT * FROM states').length,11);assert.equal(store.state('AAPL'),null);assert.equal(store.q("SELECT status FROM claims WHERE symbol='AAPL'")[0].status,'DATA_ERROR');db.close();
});
test('429 stops all further collection; 401/403 global two-denial circuit',async()=> {
  for(const status of [429,403]) {
    const {engine,store,db}=fresh();let calls=0;
    const mock=new MockYahoo();const collector={collect:async(s:string)=>({...await mock.collect(s),status:(++calls<=2?status:200)})};const runner=new Coordinator(store,collector);
    runner.start(target,start);await runner.tick(target,start);await runner.tick(target,start+35000);await runner.tick(target,start+70000);
    assert.equal(calls,status===429?1:2);assert.equal(store.q('SELECT status FROM runs')[0].status,'DATA_ERROR');db.close();
  }
});
for(const kind of ['hash','missing','schema'])test('corrupted '+kind+' state fails closed before next requests',async()=> {
  const {engine,store,mock,db}=fresh();engine.start(target,start);await finish(engine);const before=mock.calls.length;
  if(kind==='hash')store.q("UPDATE states SET body='{}' WHERE symbol='NVDA'");
  else if(kind==='missing')store.q("DELETE FROM states WHERE symbol='NVDA'");
  else store.q("UPDATE meta SET value='999' WHERE key='schema'");
  assert.throws(()=>engine.start('2026-11-09',Date.parse('2026-11-10T00:00:00Z')),/STATE_ERROR/);assert.equal(mock.calls.length,before);assert.throws(()=>store.initialize(),/REFUSED/);db.close();
});
test('missing real sessions require catchup and do not synthesize captures',async()=> {
  const {engine,store,mock,db}=fresh();engine.start(target,start);await finish(engine);const before=mock.calls.length;
  const date='2026-11-10',now=Date.parse('2026-11-11T00:00:00Z');engine.start(date,now);await finish(engine,date,now);assert.equal(mock.calls.length,before);assert.equal(store.q("SELECT * FROM claims WHERE status='CATCHUP_REQUIRED'").length,12);assert.equal(store.state('NVDA')!.doc.trading_date,target);db.close();
});
test('explicit selected backup repairs missing state without forgetting claims',async()=> {
  const {engine,store,mock,db}=fresh();engine.start(target,start);await finish(engine);const original=store.q('SELECT * FROM states');store.backup('verified');assert.throws(()=>store.restore('verified'),/EXPLICIT/);
  store.q("DELETE FROM states WHERE symbol='NVDA'");assert.throws(()=>store.state('NVDA'),/MISSING/);store.restore('verified',true);assert.deepEqual(store.q('SELECT * FROM states'),original);assert.equal(engine.start(target,start),'DUPLICATE');assert.equal(mock.calls.length,12);db.close();
});
test('pending stays sticky, rejected requires reopen, revision escalates with audit; thresholds not consumed',async()=> {
  const event={symbol:'NVDA',trading_date:target,event_type:'THRESHOLD_CROSSING',threshold:20,status:'PENDING_REVIEW',evidence:{x:1}},ledger:R={},id=await stableId(event);register(ledger,id,event);register(ledger,id,{...event,status:'CONFIRMED',evidence:{x:2}});assert.equal(ledger[id].status,'PENDING_REVIEW');assert.equal(ledger[id].evidence_versions.length,2);
  ledger[id].status='REJECTED';assert.throws(()=>register(ledger,id,{...event,evidence:{x:3}}),/REOPEN/);
  const rev={...event,event_type:'REVISION_OBSERVATION',threshold:null,status:'CONFIRMED'};const rid=await stableId(rev);register(ledger,rid,rev);assert.throws(()=>register(ledger,rid,{...rev,status:'PENDING_REVIEW',evidence:{x:4}}),/RISK/);register(ledger,rid,{...rev,status:'PENDING_REVIEW',evidence:{revision_observation:{requires_review:true}}});assert.equal(ledger[rid].status,'PENDING_REVIEW');assert.equal(ledger[rid].audit_trail.at(-1).action,'RISK_ESCALATION');
});
test('all seven legacy pending records survive imported storage without promotion or ID regeneration',()=> {
  const {store,db}=fresh(),pending=JSON.parse(readFileSync(new URL('../fixtures/legacy-pending.json',import.meta.url),'utf8'));
  for(const [id,e] of Object.entries(pending)){const body=canonical(e);store.q('INSERT INTO events VALUES (?,?,?,?)','stocks',id,body,digest(body));}
  assert.equal(Object.keys(pending).length,7);assert.deepEqual(store.ledger('NVDA'),pending);db.close();
});
test('read APIs are pure and exclude evidence, accounts, checkpoint details; validate paging and range',async()=> {
  const {engine,store,db}=fresh();engine.start(target,start);await finish(engine);
  const snapshot=()=>canonical(Object.fromEntries(['meta','states','events','claims','evidence','runs','history','backups'].map(t=>[t,store.q(`SELECT * FROM ${t}`)])));
  const before=snapshot();
  for(const route of ['/api/overview','/api/assets/NVDA','/api/assets/%5ESOX/history?limit=1','/api/events','/api/runs/latest','/api/health']) {
    const response=api(store,new Request('http://local'+route));assert.equal(response.status,200);const text=await response.text();assert.ok(!/history_prices|identity_snapshot|evidence_versions|account_id|raw_hash/.test(text));
  }
  assert.equal(api(store,new Request('http://local/api/events?limit=-1')).status,400);assert.equal(api(store,new Request('http://local/api/events?from=2026-11-06&to=2026-01-01')).status,400);
  assert.equal(api(store,new Request('http://local/api/assets/LLY')).status,404);assert.equal(api(store,new Request('http://local/api/overview',{method:'POST'})).status,405);assert.equal(snapshot(),before);db.close();
});
test('later history cannot impersonate a trusted original capture; plan is read-only',()=> {
  const plan=gapPlan('2026-11-06','2026-11-11');assert.deepEqual(plan.missing_sessions,['2026-11-09','2026-11-10']);assert.equal(plan.state_updated,false);assert.equal(plan.event_status,'PENDING_REVIEW');
  assert.throws(()=>validateArchive('raw',digest('raw'),'2026-11-11T00:00:00Z','2026-11-07T00:00:00Z','trust'),/RECONSTRUCTED/);
  assert.throws(()=>validateArchive('changed',digest('raw'),'2026-11-07T00:00:00Z','2026-11-07T00:00:00Z','trust'),/PROVENANCE/);
  assert.equal(validateArchive('raw',digest('raw'),'2026-11-07T00:00:00Z','2026-11-07T00:00:01Z','operator inspected original').origin,'TRUSTED_ARCHIVE');
});
test('slow durable sync and slow response do not shorten global network pacing',async()=> {
  const {store,db}=fresh(),mock=new MockYahoo();const engine=new Coordinator(store,mock,()=>start+20000);engine.start(target,start);await engine.tick(target,start);assert.equal(await engine.tick(target,start+24999),'WAIT');assert.equal(await engine.tick(target,start+25000),'COMMITTED');db.close();
});
test('overlapping execution ticks never issue a second request or overwrite uncertain status',async()=> {
  const {store,db}=fresh(),mock=new MockYahoo();let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  const runner=new Coordinator(store,{collect:async s=>{await gate;return mock.collect(s);}});
  runner.start(target,start);const first=runner.tick(target,start);assert.equal(await runner.tick(target,start),'UNCERTAIN_EXECUTION');release();assert.equal(await first,'UNCERTAIN_EXECUTION');
  assert.equal(mock.calls.length,1);assert.equal(store.q('SELECT * FROM states').length,0);assert.equal(store.q("SELECT status FROM claims WHERE symbol='NVDA'")[0].status,'UNCERTAIN_EXECUTION');assert.equal(store.q('SELECT * FROM evidence').length,1);db.close();
});
