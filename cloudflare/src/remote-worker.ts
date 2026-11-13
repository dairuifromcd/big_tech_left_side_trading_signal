import {DurableObject} from 'cloudflare:workers';
import {timingSafeEqual} from 'node:crypto';
import {Store,digest} from './storage.ts';
import {api} from './api.ts';
import {authorizeInitialization,makeReceipt,InitializationCommand,InitializationPolicy} from './initialization.ts';
import {RemoteHarness,WindowPlan,validateWindow} from './remote-harness.ts';

const OBJECT_NAME='phase51b-synthetic-20261113-v1';
export interface RemoteEnv extends InitializationPolicy {
  COORDINATOR:DurableObjectNamespace<RemoteMockCoordinator>;
  REMOTE_MOCK_ENABLED?:string; MOCK_START_UTC?:string; MOCK_END_UTC?:string; MOCK_INIT_END_UTC?:string;
  MOCK_CONTROL_TOKEN?:string; REPORT_TOKEN?:string;
}
function plan(env:RemoteEnv):WindowPlan {return {start:Date.parse(env.MOCK_START_UTC??''),end:Date.parse(env.MOCK_END_UTC??''),initEnd:Date.parse(env.MOCK_INIT_END_UTC??'')};}
function enabled(env:RemoteEnv) {if(env.REMOTE_MOCK_ENABLED!=='EXPLICIT_PHASE51B_MOCK_V1')throw Error('REMOTE_MOCK_DISABLED');}
function token(expected:string|undefined,supplied:string) {return !!expected&&expected.length>=32&&timingSafeEqual(Buffer.from(digest(expected)),Buffer.from(digest(supplied)));}
function control(env:RemoteEnv,credential:string) {
  enabled(env);if(!token(env.MOCK_CONTROL_TOKEN,credential))throw Error('UNAUTHORIZED');
  // Allow a bounded one-hour stop/status grace period. This cannot extend the
  // persisted collection/init window or resume a stopped experiment.
  const p=plan(env);validateWindow(p,p.start);
  if(Date.now()<p.start||Date.now()>=p.end+3600000)throw Error('CONTROL_EXPIRED');
}
export class RemoteMockCoordinator extends DurableObject<RemoteEnv> {
  readonly store:Store;readonly harness:RemoteHarness;
  constructor(ctx:DurableObjectState,env:RemoteEnv) {super(ctx,env);this.store=new Store(ctx.storage,ctx.id.toString(),'MOCK_ONLY_SYNTHETIC_V1');this.harness=new RemoteHarness(this.store,plan(env),()=>Date.now(),()=>ctx.storage.sync());}
  async identity(credential:string) {
    control(this.env,credential);
    return {object_id:this.ctx.id.toString(),initialized:this.store.initialized(),
      empty_sql:this.store.q("SELECT name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").length===0,
      empty_native:(await this.ctx.storage.list({limit:1})).size===0,alarm:await this.ctx.storage.getAlarm()};
  }
  async initializeIsolatedMock(command:InitializationCommand,credential:string) {
    enabled(this.env);validateWindow(plan(this.env),Date.now(),true);
    authorizeInitialization(this.env,this.ctx.id.toString(),command,credential);
    const outcome=await this.ctx.blockConcurrencyWhile(async()=> {
      try {
        // Recheck time inside the input gate, including slow platform storage.
        validateWindow(plan(this.env),Date.now(),true);
        if((await this.ctx.storage.list({limit:1})).size||await this.ctx.storage.getAlarm()!==null)throw Error('INITIALIZATION_REFUSED');
        const receipt=makeReceipt(command);
        this.store.initialize(receipt,undefined,()=>this.harness.bootstrap());await this.ctx.storage.sync();
        return {receipt_id:receipt.receipt_id,initialized_at_utc:receipt.initialized_at_utc,mode:'MOCK_ONLY_SYNTHETIC_V1'};
      }catch{return {error:'INITIALIZATION_REFUSED'};}
    });
    if('error' in outcome)throw Error(outcome.error);return outcome;
  }
  async startFixture(fixture:string,credential:string) {
    control(this.env,credential);const result=this.harness.start(fixture);await this.ctx.storage.sync();await this.arm();return result;
  }
  async stopExperiment(credential:string) {
    control(this.env,credential);this.harness.stop();await this.ctx.storage.sync();await this.ctx.storage.deleteAlarm();return this.harness.read();
  }
  async status(credential:string) {
    control(this.env,credential);return {experiment:this.harness.read(),alarm:await this.ctx.storage.getAlarm(),
      runs:this.store.q('SELECT * FROM runs ORDER BY date'),claims:this.store.q('SELECT date,symbol,ordinal,status,started,finished,error FROM claims ORDER BY date,ordinal'),
      receipt:JSON.parse(this.store.q("SELECT value FROM meta WHERE key='receipt'")[0].value),
      sql_reads_local_counter:this.store.reads,sql_writes_local_counter:this.store.writes,sqlite_bytes:this.ctx.storage.sql.databaseSize,
      cloud_cpu:'NOT_VERIFIED',mode:'MOCK_ONLY_SYNTHETIC_V1'};
  }
  async report(request:Request,credential:string) {
    enabled(this.env);if(!token(this.env.REPORT_TOKEN,credential))throw Error('UNAUTHORIZED');
    const response=api(this.store,request),body:any=await response.json();
    return Response.json({...body,mode:'DRY_RUN_REMOTE_MOCK_ONLY',provenance:'SYNTHETIC_NOT_HISTORICAL_PIT',
      execution:this.harness.read()}, {status:response.status,headers:response.headers});
  }
  private async arm() {const next=this.harness.nextAlarm();if(next===null)await this.ctx.storage.deleteAlarm();else await this.ctx.storage.setAlarm(next);}
  async alarm() {
    try {enabled(this.env);await this.harness.tick();await this.arm();}
    catch {try{this.harness.stop('ADAPTER_FAILURE');}catch{}await this.ctx.storage.deleteAlarm();}
  }
}
const headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'};
export default {
  async fetch(request:Request,env:RemoteEnv) {
    const url=new URL(request.url),path=url.pathname,credential=request.headers.get('Authorization')?.match(/^Bearer (.+)$/)?.[1]??'';
    try {
      enabled(env);
      if(path.startsWith('/api/')) {
        if(!token(env.REPORT_TOKEN,credential))return Response.json({error:'UNAUTHORIZED'},{status:401,headers});
        if(request.method!=='GET')return Response.json({error:'READ_ONLY'},{status:405,headers});
        return env.COORDINATOR.getByName(OBJECT_NAME).report(request,credential);
      }
      // Temporary admin bridge in this one Worker; never routes to arbitrary
      // objects, SQL, fixture timestamps, fault hooks, URLs or local-test RPCs.
      const init=path==='/_mock/initialize';
      if(init) {if(!token(env.MOCK_INIT_TOKEN,credential))throw Error('UNAUTHORIZED');validateWindow(plan(env),Date.now(),true);}
      else control(env,credential);
      if(!['/_mock/identity','/_mock/status','/_mock/initialize','/_mock/start','/_mock/stop'].includes(path))return Response.json({error:'NOT_FOUND'},{status:404,headers});
      const read=['/_mock/identity','/_mock/status'].includes(path);
      if(request.method!==(read?'GET':'POST'))return Response.json({error:'METHOD_NOT_ALLOWED'},{status:405,headers});
      const stub=env.COORDINATOR.getByName(OBJECT_NAME);
      if(path==='/_mock/identity')return Response.json(await stub.identity(credential),{headers});
      if(path==='/_mock/status')return Response.json(await stub.status(credential),{headers});
      // Bound actual streaming body bytes, not just a spoofable Content-Length.
      const reader=request.body?.getReader();let bytes=0,parts:Uint8Array[]=[];
      if(reader)for(;;){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>4096){await reader.cancel();return Response.json({error:'BODY_TOO_LARGE'},{status:413,headers});}parts.push(value);}
      const data=new Uint8Array(bytes);let offset=0;for(const part of parts){data.set(part,offset);offset+=part.byteLength;}
      const body=JSON.parse(new TextDecoder().decode(data)||'{}');
      if(init)return Response.json(await stub.initializeIsolatedMock(body,credential),{headers});
      if(path==='/_mock/stop') {if(Object.keys(body).length)throw Error('INVALID_COMMAND');return Response.json(await stub.stopExperiment(credential),{headers});}
      if(Object.keys(body).length!==1||typeof body.fixture_date!=='string')throw Error('INVALID_COMMAND');
      return Response.json({result:await stub.startFixture(body.fixture_date,credential)},{headers});
    }catch{return Response.json({error:'MOCK_REQUEST_REFUSED'},{status:403,headers});}
  }
} satisfies ExportedHandler<RemoteEnv>;
