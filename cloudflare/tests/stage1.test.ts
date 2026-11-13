import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {build} from 'esbuild';
import {OBJECT_NAME,windowBindings,probes,request} from './stage1-fixture.ts';
import {writeTestResult} from './test-output.ts';

// Execute the real entrypoint in Node with only the platform base class replaced.
const code=(await build({entryPoints:['src/remote-worker.ts'],bundle:true,write:false,format:'esm',platform:'node',plugins:[{
  name:'local-platform-base',setup(build){
    build.onResolve({filter:/^cloudflare:workers$/},()=>({path:'platform',namespace:'local'}));
    build.onLoad({filter:/.*/,namespace:'local'},()=>({contents:'export class DurableObject {constructor(ctx,env){this.ctx=ctx;this.env=env;}}'}));
  }
}]})).outputFiles[0].text;
const remote:any=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));

test('Stage1 real HTTP and RPC entrypoint in Node SQLite: no writes on any probe',async t=> {
  const control=randomBytes(40).toString('hex'),report=randomBytes(40).toString('hex');
  const start=Date.parse('2026-11-15T22:00:00Z'),realNow=Date.now,realFetch=globalThis.fetch;
  let now=start+60000,outbound=0,mutations=0,alarm:number|null=null;
  Date.now=()=>now;globalThis.fetch=async()=>{outbound++;throw Error('EXTERNAL_NETWORK_FORBIDDEN');};
  const db=new DatabaseSync(':memory:'),native=new Map();
  const storage={sql:{exec(sql:string,...args:any[]){if(!/^SELECT\b/i.test(sql))mutations++;return {toArray:()=>db.prepare(sql).all(...args)};}},
    transactionSync(fn:()=>any){mutations++;db.exec('BEGIN');try{const r=fn();db.exec('COMMIT');return r;}catch(e){db.exec('ROLLBACK');throw e;}},
    async list(){return native;},async getAlarm(){return alarm;},async setAlarm(n:number){mutations++;alarm=n;},
    async deleteAlarm(){mutations++;alarm=null;},async sync(){mutations++;}};
  const ctx={storage,id:{toString:()=> 'LOCAL_FIXED_ID'},blockConcurrencyWhile:async(fn:()=>any)=>fn()};
  let stub:any;
  const env:any={...windowBindings(start),MOCK_CONTROL_TOKEN:control,REPORT_TOKEN:report,COORDINATOR:{getByName(name:string){assert.equal(name,OBJECT_NAME);return stub;}}};
  stub=new remote.RemoteMockCoordinator(ctx,env);
  const snapshot=()=>({schema:db.prepare("SELECT * FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' ORDER BY name").all(),changes:db.prepare('SELECT total_changes() n').get(),native:[...native],alarm,mutations,collectors:stub.harness.source.calls.length});
  const empty=snapshot();let count=0;
  async function check(name:string,fn:()=>any){await t.test(name,async()=>{await fn();assert.deepEqual(snapshot(),empty);assert.equal(outbound,0);count++;});}
  try {
    for(const p of probes(control,report))await check(p.name,async()=>assert.equal((await remote.default.fetch(request(p),env)).status,p.status));
    for(const value of [undefined,'DISABLED_PENDING_GATE_B','typo'])await check('default/unknown enable refuses '+value,async()=>{
      env.REMOTE_MOCK_ENABLED=value;assert.equal((await remote.default.fetch(request({name:'',path:'/_mock/identity',token:control,status:403}),env)).status,403);Object.assign(env,windowBindings(start));
    });
    for(const value of [undefined,'short'])await check('missing/short configured control token '+value,async()=>{
      env.MOCK_CONTROL_TOKEN=value;await assert.rejects(()=>stub.identity(value??control));env.MOCK_CONTROL_TOKEN=control;
    });
    for(const offset of [-1,0,60000,1200000,86400000-1,86400000,86400000+1,90000000])await check('exact Stage1 window offset '+offset,async()=>{
      now=start+offset;const r=await remote.default.fetch(request({name:'',path:'/_mock/identity',token:control,status:200}),env);
      assert.equal(r.status,offset>=0&&offset<86400000?200:403);
      if(r.status===200)assert.deepEqual(await r.json(),{object_id:'LOCAL_FIXED_ID',initialized:false,empty_sql:true,empty_native:true,alarm:null});
    });
    now=start+60000;
    await check('repeated identity and coordinator replacement preserve empty state',async()=>{
      const before=await stub.identity(control);for(let i=0;i<3;i++)assert.deepEqual(await stub.identity(control),before);
      stub=new remote.RemoteMockCoordinator(ctx,env);assert.deepEqual(await stub.identity(control),before);
    });
    for(const [name,invoke] of [
      ['initialize',()=>stub.initializeIsolatedMock({},control)],['start fixture',()=>stub.startFixture('2026-11-06',control)],
      ['start arbitrary fixture',()=>stub.startFixture('2099-01-01',control)],['stop',()=>stub.stopExperiment(control)],
      ['status',()=>stub.status(control)],['report',()=>stub.report(new Request('https://stage1.invalid/api/overview'),report)],
    ] as const)await check('direct RPC refuses '+name,()=>assert.rejects(invoke,/STAGE1_IDENTITY_ONLY/));
    await check('Stage1 initialization stays disabled even with accidentally injected H01 fields',async()=>{
      Object.assign(env,{MOCK_INIT_ENABLED:'EXPLICIT_ISOLATED_MOCK_V1',MOCK_INIT_OBJECT_ID:'LOCAL_FIXED_ID',MOCK_INIT_TOKEN:control});
      await assert.rejects(()=>stub.initializeIsolatedMock({},control),/STAGE1_IDENTITY_ONLY/);
      for(const key of ['MOCK_INIT_ENABLED','MOCK_INIT_OBJECT_ID','MOCK_INIT_TOKEN'])delete env[key];
    });
    await check('stale Alarm callback is inert',()=>stub.alarm());
    await check('no SQL or local test RPC',()=>{assert.equal(typeof stub.testQuery,'undefined');assert.equal(typeof stub.initializeLocalMock,'undefined');});
    writeTestResult('stage1_node_results.json',{status:'PASS',checks:count,environment:'LOCAL_NODE_REAL_ENTRYPOINT_SQLITE',sql_and_native_empty:true,receipt_absent:true,application_tables:[],mutations,collector_calls:0,outbound_requests:outbound,alarm,credentials:'RANDOM_TEST_PROCESS_ONLY_NOT_RECORDED'});
  }finally{Date.now=realNow;globalThis.fetch=realFetch;db.close();}
});
