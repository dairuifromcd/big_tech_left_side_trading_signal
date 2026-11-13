import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {Store,canonical} from '../src/storage.ts';
import {RemoteHarness,validateWindow,WindowPlan} from '../src/remote-harness.ts';
import {FIXTURE_DATES,SyntheticCollector} from '../src/synthetic.ts';
import {Coordinator} from '../src/coordinator.ts';
import {api} from '../src/api.ts';
import {SYMBOLS} from '../src/core.ts';
import {validateYahoo} from '../src/yahoo.ts';
import {makeReceipt} from '../src/initialization.ts';
import {writeTestResult} from './test-output.ts';

const START=Date.parse('2026-11-13T00:00:00Z');
const PLAN:WindowPlan={start:START,end:START+86400000,initEnd:START+1200000};
function fixture() {
  const db=new DatabaseSync(':memory:');let now=START+60000;
  const store=new Store({sql:{exec(sql,...args){const rows=db.prepare(sql).all(...args);return {toArray:()=>rows};}},transactionSync(fn){db.exec('BEGIN');try{const r=fn();db.exec('COMMIT');return r;}catch(e){db.exec('ROLLBACK');throw e;}}},undefined,'MOCK_ONLY_SYNTHETIC_V1');
  const harness=new RemoteHarness(store,PLAN,()=>now,async()=>{});
  const initialize=()=>store.initialize(makeReceipt({operation:'INITIALIZE_EMPTY_ISOLATED_MOCK',target_object_id:'LOCAL_TEST',request_id:'local',operator:'LOCAL',authorization_reference:'LOCAL',reason:'synthetic bounded harness'}),undefined,()=>harness.bootstrap());
  return {db,store,harness,initialize,setTime:(t:number)=>{now=t;},clock:()=>now};
}
const snapshot=(s:Store)=>canonical(s.q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*' ORDER BY name").map(t=>[t.name,s.q(`SELECT * FROM ${t.name}`)]));
for(const symbol of SYMBOLS)test(`synthetic identity and date validation ${symbol}`,async()=> {
  for(const date of FIXTURE_DATES){const r=await new SyntheticCollector().collect(symbol,date),s=validateYahoo(symbol,JSON.parse(r.raw),r.asof);assert.equal(s.target,date);assert.equal(s.identity.provenance,'MOCK_ONLY_SYNTHETIC_V1');}
});
test('two full runs use real pacing with explicit fixture dates, <=80 alarms and exactly24 calls',async()=> {
  const f=fixture();f.initialize();const {harness:h,store:s}=f;
  const starts:number[]=[];
  for(const date of FIXTURE_DATES) {
    assert.equal(h.start(date),'STARTED');assert.equal(h.start(date),'DUPLICATE');
    for(let i=0;i<40;i++) {
      const next=h.nextAlarm();assert.notEqual(next,null);f.setTime(next!);const result=await h.tick();
      if(result==='COMPLETE')break;
      assert.equal(result,'COMMITTED');
    }
    assert.equal(s.q('SELECT status FROM runs WHERE date=?',date)[0].status,'COMPLETE');
    const claims=s.q('SELECT * FROM claims WHERE date=? ORDER BY ordinal',date);
    assert.deepEqual(claims.map(c=>c.symbol),SYMBOLS);
    for(let i=1;i<claims.length;i++)assert.ok(claims[i].started-claims[i-1].finished>=5000+(i%3===0?30000:0));
    starts.push(claims[0].started);s.validateFullCheckpoint();
  }
  assert.equal(h.read().runs,2);assert.equal(h.read().collectors,24);assert.equal(h.read().alarms,26);assert.equal(h.source.calls.length,24);
  assert.equal(h.read().status,'STOPPED');assert.equal(h.nextAlarm(),null);assert.equal(s.q('SELECT count(*) AS n FROM states')[0].n,12);
  assert.equal(s.q('SELECT count(*) AS n FROM evidence')[0].n,24);assert.equal(s.q('SELECT count(*) AS n FROM events')[0].n,0);
  assert.ok(s.q('SELECT origin FROM evidence').every(row=>row.origin==='MOCK_ONLY_SYNTHETIC_V1'));
  assert.equal(s.state('^SOX')!.doc.watch_tier,'WATCH_30');
  const before=snapshot(s);
  for(const path of ['/api/overview','/api/runs/latest','/api/health','/api/events','/api/assets/NVDA','/api/assets/NVDA/history'])assert.equal(api(s,new Request('https://mock.invalid'+path)).status,200);
  assert.equal(snapshot(s),before);
  assert.throws(()=>h.start(FIXTURE_DATES[0]),/STOPPED/);
  writeTestResult('remote_mock_local_results.json',{environment:'LOCAL_NODE_SQLITE_SYNTHETIC_ONLY',runs:2,collector_calls:24,alarm_ticks:26,events:0,sox_watch:'WATCH_30',full_checkpoint:'PASS',reports_read_only:6,execution_clock:'INJECTED_LOCAL_SIMULATION_NOT_ACTUAL_UTC',simulated_execution_clock_starts:starts.map(t=>new Date(t).toISOString()),fixtures:FIXTURE_DATES,real_yahoo_requests:0,cloud_metrics:'NOT_VERIFIED',
    local_sql_statements:s.statements,local_query_rows_returned:s.reads,local_sqlite_page_bytes:f.db.prepare('PRAGMA page_count').get()!['page_count'] as number*(f.db.prepare('PRAGMA page_size').get()!['page_size'] as number)});
});
test('production Coordinator still rejects archived date against actual execution time',()=> {const f=fixture();f.initialize();assert.throws(()=>new Coordinator(f.store,new SyntheticCollector()).start(FIXTURE_DATES[0],f.clock()),/INVALID_TARGET_SESSION/);});
test('initialization and budget bootstrap are atomic on adapter failure',()=> {
  const f=fixture();assert.throws(()=>f.store.initialize(undefined,undefined,()=>{f.harness.bootstrap();throw Error('BOOTSTRAP_FAILURE');}),/BOOTSTRAP_FAILURE/);
  assert.equal(f.store.q("SELECT name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").length,0);f.initialize();assert.equal(f.harness.read().collectors,0);
});
test('init expiry refuses schema creation',()=> {const f=fixture();f.setTime(PLAN.initEnd);assert.throws(f.initialize,/WINDOW_CLOSED/);assert.equal(f.store.initialized(),false);});
for(const t of [PLAN.start-1,PLAN.end,PLAN.end+1])test(`window rejects ${t}`,()=>assert.throws(()=>validateWindow(PLAN,t),/WINDOW_CLOSED/));
test('window cannot be longer than24h or init longer than20min',()=> {
  assert.throws(()=>validateWindow({...PLAN,end:PLAN.end+1},START),/INVALID/);assert.throws(()=>validateWindow({...PLAN,initEnd:PLAN.initEnd+1},START),/INVALID/);
});
test('stop persists across adapter replacement and prohibits collection',async()=> {
  const f=fixture();f.initialize();f.harness.start(FIXTURE_DATES[0]);f.harness.stop();
  const fresh=new RemoteHarness(f.store,PLAN,f.clock,async()=>{});await fresh.tick();assert.equal(fresh.source.calls.length,0);assert.equal(fresh.read().status,'STOPPED');assert.equal(fresh.nextAlarm(),null);assert.throws(()=>fresh.start(FIXTURE_DATES[1]),/STOPPED/);
});
test('deadline before next alarm stops without collection',async()=> {const f=fixture();f.initialize();f.harness.start(FIXTURE_DATES[0]);f.setTime(PLAN.end);assert.equal(await f.harness.tick(),'STOPPED');assert.equal(f.harness.source.calls.length,0);assert.equal(f.harness.nextAlarm(),null);});
test('expiry during durable sync blocks collector even after attempt charged',async()=> {
  const f=fixture();f.initialize();let calls=0;
  const h=new RemoteHarness(f.store,PLAN,f.clock,async()=>{if(++calls===2)f.setTime(PLAN.end);});h.start(FIXTURE_DATES[0]);await h.tick();assert.equal(h.source.calls.length,0);assert.equal(h.read().collectors,1);assert.equal(h.nextAlarm(),null);
});
test('persisted alarm budget stops repeated early callbacks',async()=> {
  const f=fixture();f.initialize();const h=f.harness;h.start(FIXTURE_DATES[0]);await h.tick();
  for(let i=0;i<79;i++)await h.tick();
  assert.equal(h.read().status,'STOPPED');assert.equal(h.read().alarms,80);
  for(let i=0;i<11;i++)await h.tick();
  assert.equal(h.read().alarms,80);assert.equal(h.source.calls.length,1);assert.equal(h.nextAlarm(),null);assert.equal(h.read().status,'STOPPED');
});
test('overlapping, reversed and arbitrary fixture requests are rejected',()=> {const f=fixture();f.initialize();assert.throws(()=>f.harness.start(FIXTURE_DATES[1]),/ORDER/);assert.throws(()=>f.harness.start('2026-11-12'),/NOT_ALLOWED/);f.harness.start(FIXTURE_DATES[0]);assert.throws(()=>f.harness.start(FIXTURE_DATES[1]),/OVERLAPPING/);});
test('changed persisted budget fails closed before source invocation',async()=> {const f=fixture();f.initialize();f.harness.start(FIXTURE_DATES[0]);f.store.q("UPDATE mock_experiment SET body='{}'");assert.equal(await f.harness.tick(),'STOPPED');assert.equal(f.harness.source.calls.length,0);assert.equal(f.harness.nextAlarm(),null);});
test('redeployment cannot extend the persisted window',()=> {const f=fixture();f.initialize();const h=new RemoteHarness(f.store,{...PLAN,end:PLAN.end+1},f.clock,async()=>{});assert.throws(()=>h.start(FIXTURE_DATES[0]),/CORRUPT/);});
test('uncertain collection after durable declaration is never recollected',async()=> {
  const f=fixture();f.initialize();const h=f.harness;h.start(FIXTURE_DATES[0]);f.store.q("UPDATE claims SET status='REQUEST_CLAIMED',started=? WHERE ordinal=0",f.clock());
  assert.equal(await h.tick(),'UNCERTAIN_EXECUTION');assert.equal(h.source.calls.length,0);assert.equal(h.read().status,'STOPPED');
});
