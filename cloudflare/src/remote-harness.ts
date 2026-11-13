import {Store,canonical,digest} from './storage.ts';
import {Coordinator} from './coordinator.ts';
import {calendar} from './core.ts';
import {FIXTURE_DATES,SyntheticCollector} from './synthetic.ts';

export interface WindowPlan {start:number;end:number;initEnd:number}
export interface Budget extends WindowPlan {mode:'MOCK_ONLY_SYNTHETIC_V1';runs:number;collectors:number;alarms:number;status:'ACTIVE'|'STOPPED';reason:string;executions:{fixture_date:string;real_started_at_utc:string}[]}
export function validateWindow(p:WindowPlan,now:number,initializing=false) {
  if(![p.start,p.end,p.initEnd,now].every(Number.isSafeInteger)||p.end<=p.start||p.end-p.start>86400000||p.initEnd<=p.start||p.initEnd>p.start+1200000||p.initEnd>p.end)throw Error('INVALID_EXPERIMENT_WINDOW');
  if(now<p.start||now>=p.end||(initializing&&now>=p.initEnd))throw Error('EXPERIMENT_WINDOW_CLOSED');
}
export class RemoteHarness {
  readonly source=new SyntheticCollector();readonly engine:Coordinator;
  constructor(readonly store:Store,readonly plan:WindowPlan,readonly clock:()=>number,readonly sync:()=>Promise<void>) {
    this.engine=new Coordinator(store,{collect:async(symbol,date)=> {
      this.active();this.store.assertRequestCheckpoint(date!);
      const b=this.read();if(b.collectors>=24)throw Error('COLLECTOR_BUDGET_EXHAUSTED');
      // Charge before any await/call; crashes consume budget rather than retry.
      this.write({...b,collectors:b.collectors+1});await this.sync();
      this.active();this.store.assertRequestCheckpoint(date!);
      return this.source.collect(symbol,date);
    }},clock);
  }
  bootstrap() {
    validateWindow(this.plan,this.clock(),true);
    this.store.q('CREATE TABLE mock_experiment (id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL,hash TEXT NOT NULL)');
    const b:Budget={...this.plan,mode:'MOCK_ONLY_SYNTHETIC_V1',runs:0,collectors:0,alarms:0,status:'ACTIVE',reason:'',executions:[]};
    this.store.q('INSERT INTO mock_experiment VALUES (1,?,?)',canonical(b),digest(canonical(b)));
  }
  read():Budget {
    this.store.guard();const rows=this.store.q('SELECT * FROM mock_experiment');
    if(rows.length!==1||digest(rows[0].body)!==rows[0].hash)throw Error('EXPERIMENT_BUDGET_CORRUPT');
    const b=JSON.parse(rows[0].body) as Budget;
    if(canonical(b)!==rows[0].body||b.mode!=='MOCK_ONLY_SYNTHETIC_V1'||!['ACTIVE','STOPPED'].includes(b.status)||
      b.start!==this.plan.start||b.end!==this.plan.end||b.initEnd!==this.plan.initEnd||
      ![[b.runs,2],[b.collectors,24],[b.alarms,80]].every(([n,max])=>Number.isSafeInteger(n)&&n>=0&&n<=max)||b.executions.length!==b.runs)throw Error('EXPERIMENT_BUDGET_CORRUPT');
    return b;
  }
  private write(b:Budget) {const body=canonical(b);this.store.q('UPDATE mock_experiment SET body=?,hash=? WHERE id=1',body,digest(body));}
  active() {const b=this.read();validateWindow(b,this.clock());if(b.status!=='ACTIVE')throw Error('EXPERIMENT_STOPPED');return b;}
  stop(reason='OPERATOR_STOP') {
    const b=this.read();if(b.status!=='STOPPED')this.write({...b,status:'STOPPED',reason});
    this.store.q("UPDATE runs SET status='HALTED',updated=? WHERE status='RUNNING'",this.clock());
  }
  start(fixture:string) {
    const b=this.active();if(!FIXTURE_DATES.includes(fixture as any))throw Error('MOCK_FIXTURE_NOT_ALLOWED');
    if(this.store.q('SELECT 1 FROM runs WHERE date=?',fixture).length)return 'DUPLICATE';
    if(b.runs>=2||b.collectors>=24||b.alarms>=80)throw Error('EXPERIMENT_BUDGET_EXHAUSTED');
    if(fixture!==FIXTURE_DATES[b.runs])throw Error('FIXTURE_ORDER_REQUIRED');
    if(this.store.q("SELECT 1 FROM runs WHERE status!='COMPLETE'").length)throw Error('OVERLAPPING_OR_FAILED_RUN_BLOCKED');
    // No simulated timestamp supplied by the caller. Only this isolated adapter
    // derives one from its fixed fixture. Coordinator's real-date guard is intact.
    this.store.validateFullCheckpoint();
    this.write({...b,runs:b.runs+1,executions:[...b.executions,{fixture_date:fixture,real_started_at_utc:new Date(this.clock()).toISOString()}]});
    const result=this.engine.start(fixture,calendar[fixture]![1]+1000);
    this.store.q('UPDATE runs SET updated=? WHERE date=?',this.clock(),fixture);return result;
  }
  async tick() {
    try {
      const b=this.active();if(b.alarms>=80)throw Error('ALARM_BUDGET_EXHAUSTED');
      this.write({...b,alarms:b.alarms+1});await this.sync();this.active();
      const run=this.store.q("SELECT date FROM runs WHERE status='RUNNING' LIMIT 1")[0];
      if(!run)return 'NO_RUN';
      const result=await this.engine.tick(run.date,this.clock());
      if(['UNCERTAIN_EXECUTION','STATE_ERROR'].includes(result)||
        result==='DATA_ERROR'&&this.store.q('SELECT status FROM runs WHERE date=?',run.date)[0]?.status!=='RUNNING')this.stop(result);
      if(result==='COMPLETE'&&this.read().runs===2)this.stop('COMPLETED_TWO_RUNS');
      else if(this.read().alarms>=80)this.stop('ALARM_BUDGET_EXHAUSTED');
      return result;
    }catch(error) {
      // Swallow at the adapter boundary: never request platform automatic retries.
      try {this.stop(String((error as Error).message));}catch{/* Corrupt budgets fail closed. */}
      return 'STOPPED';
    }
  }
  nextAlarm():number|null {
    try {
      const b=this.active();if(b.alarms>=80||b.collectors>=24&& !this.store.q("SELECT 1 FROM runs WHERE status='RUNNING'").length)return null;
      const run=this.store.q("SELECT date FROM runs WHERE status='RUNNING' LIMIT 1")[0];if(!run)return null;
      const task=this.store.q("SELECT * FROM claims WHERE date=? AND status IN ('READY','EVIDENCE_SAVED') ORDER BY ordinal LIMIT 1",run.date)[0];
      const last=this.store.q('SELECT * FROM claims WHERE started IS NOT NULL ORDER BY started DESC LIMIT 1')[0];
      const wait=task?.status==='READY'&&last?(last.finished??last.started)+5000+(Math.floor(task.ordinal/3)!==Math.floor(last.ordinal/3)?30000:0):this.clock()+1;
      const next=Math.max(this.clock()+1,wait);
      // A deadline alarm persists expiry/stop even when the next task is later.
      return Math.min(next,b.end);
    }catch{return null;}
  }
}
