// Shared fault matrix; imported only by tests and the local-only test Worker.
import {Store,canonical,digest} from '../src/storage.ts';
import {RemoteHarness,WindowPlan} from '../src/remote-harness.ts';
import {FIXTURE_DATES} from '../src/synthetic.ts';
import {SYMBOLS} from '../src/core.ts';

export const ATOMIC_START=Date.parse('2026-11-13T00:00:00Z');
export const ATOMIC_PLAN:WindowPlan={start:ATOMIC_START,end:ATOMIC_START+86400000,initEnd:ATOMIC_START+1200000};
export const START_CASES=['checkpoint','budget_write','run_insert','claim_6','checkpoint_control','run_checkpoint','updated','duplicate','order','stopped','exhausted','collector_exhausted','alarm_exhausted','negative_budget','over_budget','existing_claim','overlap','window','success'] as const;
export type StartCase=typeof START_CASES[number];
function snapshot(s:Store) {
  return canonical(s.q("SELECT name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' AND name NOT GLOB '_cf_*' ORDER BY name").map(row=>[row,row.sql.startsWith('CREATE TABLE')?s.q(`SELECT * FROM ${row.name} ORDER BY rowid`):null]));
}
export function exerciseStart(s:Store,scenario:StartCase) {
  let now=ATOMIC_START+60000;
  const h=new RemoteHarness(s,ATOMIC_PLAN,()=>now,async()=>{throw Error('START_MUST_NOT_SYNC_OR_COLLECT');});
  s.initialize(undefined,undefined,()=>h.bootstrap());
  const first=FIXTURE_DATES[0];
  if(scenario==='checkpoint')s.q('UPDATE checkpoint_control SET validated_generation=-2');
  if(scenario==='duplicate'||scenario==='overlap')h.start(first);
  if(scenario==='stopped')h.stop();
  if(['exhausted','collector_exhausted','alarm_exhausted','negative_budget','over_budget'].includes(scenario)) {
    const b=h.read();
    if(scenario==='exhausted') {b.runs=2;b.executions=FIXTURE_DATES.map(fixture_date=>({fixture_date,real_started_at_utc:new Date(now).toISOString()}));}
    else if(scenario==='alarm_exhausted')b.alarms=80;
    else b.collectors=scenario==='collector_exhausted'?24:scenario==='negative_budget'?-1:25;
    const body=canonical(b);s.q('UPDATE mock_experiment SET body=?,hash=?',body,digest(body));
  }
  if(scenario==='existing_claim')s.q("INSERT INTO claims(key,date,symbol,ordinal,status) VALUES (?,?,'NVDA',0,'REQUEST_CLAIMED')",first+'/NVDA',first);
  if(scenario==='window')now=ATOMIC_PLAN.end;
  const before=snapshot(s),q=s.q.bind(s);let claims=0,faultReached=false;
  s.q=(sql:string,...args:any[])=> {
    // Throw AFTER the statement, proving rollback of partial changes too.
    const rows=q(sql,...args);
    const hit=scenario==='budget_write'&&sql.startsWith('UPDATE mock_experiment')||
      scenario==='run_insert'&&sql.startsWith('INSERT INTO runs')||
      scenario==='claim_6'&&sql.startsWith('INSERT INTO claims')&&++claims===6||
      scenario==='checkpoint_control'&&sql.startsWith('UPDATE checkpoint_control')||
      scenario==='run_checkpoint'&&sql.startsWith('INSERT INTO run_checkpoints')||
      scenario==='updated'&&sql.startsWith('UPDATE runs SET updated');
    if(hit){faultReached=true;throw Error('ATOMIC_START_INJECTED_'+scenario);}return rows;
  };
  let result:string|undefined,error='';
  try{result=h.start(scenario==='order'||scenario==='overlap'?FIXTURE_DATES[1]:first);}catch(e){error=String(e);}
  finally{s.q=q;}
  const after=snapshot(s),budget=h.read.bind(h);
  const expected=scenario==='success'?'STARTED':scenario==='duplicate'?'DUPLICATE':undefined;
  if(expected?result!==expected:!error)throw Error('UNEXPECTED_START_RESULT: '+scenario+' '+result+' '+error);
  if(scenario!=='success'&&before!==after)throw Error('DATABASE_NOT_ROLLED_BACK: '+scenario);
  if(['budget_write','run_insert','claim_6','checkpoint_control','run_checkpoint','updated'].includes(scenario)&&!faultReached)throw Error('FAULT_NOT_REACHED: '+scenario);
  if(h.source.calls.length)throw Error('COLLECTOR_CALLED_DURING_START');
  if(scenario==='success') {
    const b=budget(),runs=s.q('SELECT * FROM runs'),c=s.q('SELECT * FROM claims ORDER BY ordinal');
    if(b.runs!==1||b.executions.length!==1||b.executions[0].fixture_date!==first||b.collectors||b.alarms||runs.length!==1||runs[0].status!=='RUNNING'||runs[0].updated!==now||canonical(c.map(r=>r.symbol))!==canonical(SYMBOLS)||c.some(r=>r.status!=='READY'))throw Error('START_INCONSISTENT');
    s.assertRequestCheckpoint(first);
  }
  if(scenario==='duplicate'&&budget().runs!==1)throw Error('DUPLICATE_CHARGED');
  let retry='NOT_ATTEMPTED';
  if(faultReached) {
    retry=h.start(first);
    if(retry!=='STARTED'||budget().runs!==1||s.q('SELECT * FROM claims').length!==12)throw Error('FAILED_START_CANNOT_RETRY');
    s.assertRequestCheckpoint(first);
  }
  return {scenario,result:result??'REFUSED',error,fault_reached:faultReached,snapshot_identical:before===after,retry,collector_calls:h.source.calls.length};
}
