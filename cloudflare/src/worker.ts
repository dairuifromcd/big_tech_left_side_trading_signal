import {DurableObject} from 'cloudflare:workers';
import {Store} from './storage.ts';
import {Coordinator} from './coordinator.ts';
import {MockYahoo} from './mock.ts';
import {api} from './api.ts';
import {latestSession} from './core.ts';
interface Env {COORDINATOR:DurableObjectNamespace<ExecutionCoordinator>; REPORT_TOKEN?:string; LOCAL_TESTING?:string}
export class ExecutionCoordinator extends DurableObject<Env> {
  readonly store:Store;readonly collector:MockYahoo;readonly engine:Coordinator;
  constructor(ctx:DurableObjectState,env:Env) {
    super(ctx,env);this.store=new Store(ctx.storage);this.collector=new MockYahoo();
    this.engine=new Coordinator(this.store,{collect:async s=>{await this.ctx.storage.sync();return this.collector.collect(s);}},env.LOCAL_TESTING==='1'?null:()=>Date.now());
  }
  report(request:Request) {return api(this.store,request);}
  async start(date:string,now:number) {
    const result=this.engine.start(date,now);
    // A crash between the run transaction and setAlarm must remain resumable.
    if(this.store.q('SELECT status FROM runs WHERE date=?',date)[0]?.status==='RUNNING'&&await this.ctx.storage.getAlarm()===null)
      await this.ctx.storage.setAlarm(Date.now()+1000);
    return result;
  }
  async alarm() {
    const run=this.store.q("SELECT date FROM runs WHERE status='RUNNING' ORDER BY date LIMIT 1")[0];if(!run)return;
    await this.engine.tick(run.date,Date.now());
    if(this.store.q('SELECT status FROM runs WHERE date=?',run.date)[0]?.status==='RUNNING')await this.ctx.storage.setAlarm(Date.now()+5000);
  }
  // Internal harness RPCs require an explicit local-only binding absent from cf config.
  testGuard() {if(this.env.LOCAL_TESTING!=='1')throw Error('LOCAL_HARNESS_DISABLED');}
  testInit() {this.testGuard();this.store.initialize();}
  testStart(date:string,now:number) {this.testGuard();return this.engine.start(date,now);}
  async testTick(date:string,now:number,fault?:string) {this.testGuard();return this.engine.tick(date,now,fault);}
  testQuery(sql:string,...params:any[]) {this.testGuard();return this.store.q(sql,...params);}
  testBackup(id:string) {this.testGuard();return this.store.backup(id);}
  testRestore(id:string) {this.testGuard();return this.store.restore(id,true);}
  testCalls() {this.testGuard();return this.collector.calls;}
  async testArm(delay:number) {this.testGuard();await this.ctx.storage.setAlarm(Date.now()+delay);}
  async testCancel() {this.testGuard();await this.ctx.storage.deleteAlarm();}
  testMetrics() {
    this.testGuard();
    const bytes=(table:string,field:string)=>this.store.q(`SELECT COALESCE(SUM(length(${field})),0) AS n FROM ${table}`)[0].n;
    const sizes={state_json_bytes:bytes('states','body'),raw_envelope_bytes:bytes('evidence','raw'),history_report_bytes:bytes('history','body'),event_json_bytes:bytes('events','body')};
    return {...sizes,reads:this.store.reads,writes:this.store.writes,statements:this.store.statements,sqlite_bytes:this.ctx.storage.sql.databaseSize};
  }
}
export default {
  async fetch(request:Request,env:Env) {
    if(!env.REPORT_TOKEN||request.headers.get('Authorization')!==`Bearer ${env.REPORT_TOKEN}`)return Response.json({error:'UNAUTHORIZED'},{status:401,headers:{'Cache-Control':'no-store'}});
    if(request.method!=='GET')return Response.json({error:'READ_ONLY'},{status:405,headers:{Allow:'GET'}});
    return env.COORDINATOR.getByName('fixed-us-stocks-poc-v1').report(request);
  },
  async scheduled(controller:ScheduledController,env:Env,ctx:ExecutionContext) {
    const target=latestSession(controller.scheduledTime);
    ctx.waitUntil(env.COORDINATOR.getByName('fixed-us-stocks-poc-v1').start(target,controller.scheduledTime));
  }
} satisfies ExportedHandler<Env>;
