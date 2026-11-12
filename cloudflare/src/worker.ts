import {DurableObject} from 'cloudflare:workers';
import {Store} from './storage.ts';
import {Coordinator} from './coordinator.ts';
import {MockYahoo} from './mock.ts';
import {api} from './api.ts';
import {latestSession} from './core.ts';
import {authorizeInitialization, InitializationCommand, InitializationPolicy, makeReceipt} from './initialization.ts';
interface Env extends InitializationPolicy {COORDINATOR:DurableObjectNamespace<ExecutionCoordinator>; REPORT_TOKEN?:string; LOCAL_TESTING?:string}
export class ExecutionCoordinator extends DurableObject<Env> {
  readonly store:Store;readonly collector:MockYahoo;readonly engine:Coordinator;
  constructor(ctx:DurableObjectState,env:Env) {
    super(ctx,env);this.store=new Store(ctx.storage,ctx.id.toString());this.collector=new MockYahoo();
    this.engine=new Coordinator(this.store,{collect:async (s,date)=>{await this.ctx.storage.sync();this.store.assertRequestCheckpoint(date!);return this.collector.collect(s);}},env.LOCAL_TESTING==='1'?null:()=>Date.now());
  }
  // No HTTP route forwards here. Default config supplies none of these policy
  // bindings; a separately authorized internal caller must name this exact DO.
  async initializeIsolatedMock(command:InitializationCommand, credential:string) {
    authorizeInitialization(this.env,this.ctx.id.toString(),command,credential);
    const outcome=await this.ctx.blockConcurrencyWhile(async()=> {
      // Expected rejection must not reset an otherwise healthy DO instance.
      try {
        if((await this.ctx.storage.list({limit:1})).size || await this.ctx.storage.getAlarm()!==null)throw Error('INITIALIZATION_REFUSED: NATIVE_STORAGE_OR_ALARM');
        const receipt=makeReceipt(command);this.store.initialize(receipt);await this.ctx.storage.sync();
        return {receipt_id:receipt.receipt_id,initialized_at_utc:receipt.initialized_at_utc};
      }catch(error) {return {error:String((error as Error).message)};}
    });
    if('error' in outcome)throw Error(outcome.error);return outcome;
  }
  report(request:Request) {return api(this.store,request);}
  // Read-only internal diagnostic, not an HTTP route or an initialization path.
  mockCollectionCount() {return this.collector.calls.length;}
  async start(date:string,now:number) {
    const result=this.engine.start(date,now);
    // A crash between the run transaction and setAlarm must remain resumable.
    if(this.store.q('SELECT status FROM runs WHERE date=?',date)[0]?.status==='RUNNING'&&await this.ctx.storage.getAlarm()===null)
      await this.ctx.storage.setAlarm(Date.now()+1000);
    return result;
  }
  async alarm() {
    this.store.guard();
    const run=this.store.q("SELECT date FROM runs WHERE status='RUNNING' ORDER BY date LIMIT 1")[0];if(!run)return;
    await this.engine.tick(run.date,Date.now());
    if(this.store.q('SELECT status FROM runs WHERE date=?',run.date)[0]?.status==='RUNNING')await this.ctx.storage.setAlarm(Date.now()+5000);
  }
  // Internal harness RPCs require an explicit local-only binding absent from cf config.
  testGuard() {if(this.env.LOCAL_TESTING!=='1')throw Error('LOCAL_HARNESS_DISABLED');}
  testInit(fault?:'after_schema'|'after_receipt') {this.testGuard();this.store.initialize(makeReceipt({operation:'INITIALIZE_EMPTY_ISOLATED_MOCK',target_object_id:this.ctx.id.toString(),request_id:crypto.randomUUID(),operator:'LOCAL_OFFLINE_HARNESS',authorization_reference:'LOCAL_TEST_ONLY',reason:'Explicit local workerd test'}),fault);}
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
    return {...sizes,reads:this.store.reads,writes:this.store.writes,statements:this.store.statements,checkpoint_full_validations:this.store.fullValidations,sqlite_bytes:this.ctx.storage.sql.databaseSize};
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
