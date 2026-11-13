import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {buildSync} from 'esbuild';
import {Miniflare,MiniflareOptions} from 'miniflare';
import {newLocalPersistence} from '../scripts/local-runtime.ts';
import {writeTestResult} from './test-output.ts';
import {OBJECT_NAME,windowBindings,probes,request} from './stage1-fixture.ts';

test('Stage1 workerd SQLite: HTTP/RPC denial, empty storage and runtime restart',async t=>{
  const full=process.env.STAGE1_FULL_OUTPUT==='1',path=newLocalPersistence();let outbound=0,count=0;
  const control=randomBytes(40).toString('hex'),report=randomBytes(40).toString('hex');
  const start=Date.now()-1000,bindings={...windowBindings(start),MOCK_CONTROL_TOKEN:control,REPORT_TOKEN:report};
  // The observer exists only in this locally compiled test artifact. Full output
  // verification below executes the actual unmodified cf deployment bundle.
  const contents=full?readFileSync('.cloudflare/output/v0/workers/default/bundle/index.js','utf8'):buildSync({stdin:{
    contents:`import worker,{RemoteMockCoordinator as Base} from './src/remote-worker.ts';
      export class RemoteMockCoordinator extends Base {async inspect(){return {schema:this.store.q("SELECT * FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' ORDER BY name"),changes:this.store.q('SELECT total_changes() n'),native:[...await this.ctx.storage.list()],alarm:await this.ctx.storage.getAlarm(),collectors:this.harness.source.calls.length};}} export default worker;`,
    resolveDir:process.cwd()},bundle:true,write:false,format:'esm',platform:'neutral',external:['cloudflare:workers','node:crypto']}).outputFiles[0].text;
  const config=full?JSON.parse(readFileSync('.cloudflare/output/v0/workers/default/worker.config.json','utf8')):{
    name:'us-stocks-p51b-mock-20261113',compatibilityDate:'2026-11-10',compatibilityFlags:['nodejs_compat'],
    exports:{RemoteMockCoordinator:{type:'durable-object',storage:'sqlite'}},env:{COORDINATOR:{type:'durable-object',worker:'us-stocks-p51b-mock-20261113',exportName:'RemoteMockCoordinator'}}};
  if(full)assert.equal(config.env.REMOTE_MOCK_ENABLED.value,bindings.REMOTE_MOCK_ENABLED);
  function options(values:Record<string,string>):MiniflareOptions{return {host:'127.0.0.1',port:0,cf:false,telemetry:{enabled:false},enableDevRegistry:false,
    resourcePersistencePath:path,resourceTmpPath:resolve('.tmp'),workers:[{config:{...config,
      manifest:{mainModule:'index.js',modules:{'index.js':{type:'esm',contents}}},env:{COORDINATOR:config.env.COORDINATOR,
        ...Object.fromEntries(Object.entries(values).map(([key,value])=>[key,{type:'text',value}]))}},
      dev:{outboundService:{type:'fetcher',handler:()=>{outbound++;throw Error('EXTERNAL_NETWORK_FORBIDDEN');}}}}]};}
  let mf=new Miniflare(options(bindings)),stub:any,id:string,empty:any;
  const plain=async(value:any)=>JSON.parse(JSON.stringify(await value));
  const readIdentity=()=>plain(stub.identity(control));
  const inspect=()=>full?readIdentity():plain(stub.inspect());
  const identity=()=>mf.dispatchFetch('https://stage1.invalid/_mock/identity',{headers:{Authorization:'Bearer '+control}});
  async function reset(values:Record<string,string>){await mf.setOptions(options(values));stub=(await mf.getDurableObjectNamespace('COORDINATOR')).getByName(OBJECT_NAME);}
  async function check(name:string,fn:()=>any){await t.test(name,async()=>{await fn();assert.equal(outbound,0);if(!full)assert.deepEqual(await inspect(),empty);count++;});}
  try {
    await mf.ready;const ns=await mf.getDurableObjectNamespace('COORDINATOR');stub=ns.getByName(OBJECT_NAME);id=ns.idFromName(OBJECT_NAME).toString();empty=await inspect();
    const expected={object_id:id,initialized:false,empty_sql:true,empty_native:true,alarm:null};
    await check('valid control reads fixed identity without application initialization',async()=>assert.deepEqual(await (await identity()).json(),expected));
    for(const p of probes(control,report))await check(p.name,async()=>{const req=request(p);const r=await mf.dispatchFetch(req.url,{method:req.method,headers:Object.fromEntries(req.headers.entries()),...(req.body?{body:await req.text()}:{})});assert.equal(r.status,p.status);assert.deepEqual(await readIdentity(),expected);});
    for(const [name,invoke] of [
      ['initialize',()=>stub.initializeIsolatedMock({},control)],['start',()=>stub.startFixture('2026-11-06',control)],
      ['arbitrary fixture',()=>stub.startFixture('2099-01-01',control)],['stop',()=>stub.stopExperiment(control)],['status',()=>stub.status(control)],
    ] as const)await check('direct RPC refuses '+name,()=>assert.rejects(invoke));
    await check('SQL/local test RPC missing',async()=>{await assert.rejects(async()=>await stub.testQuery('CREATE TABLE injected(x)'));await assert.rejects(async()=>await stub.initializeLocalMock());});
    for(const [name,extra] of [
      ['disabled mode',{REMOTE_MOCK_ENABLED:'DISABLED_PENDING_GATE_B'}],
      ['missing control',{MOCK_CONTROL_TOKEN:''}],['short control',{MOCK_CONTROL_TOKEN:'short'}],
      ['before start',windowBindings(Date.now()+60000)],['after end',windowBindings(Date.now()-86400000-1000)],
    ] as const)await check(name,async()=>{await reset({...bindings,...extra});assert.equal((await identity()).status,403);await reset(bindings);assert.deepEqual(await readIdentity(),expected);});
    await check('accidental H01 fields do not enable Stage1 initialize',async()=>{
      await reset({...bindings,MOCK_INIT_ENABLED:'EXPLICIT_ISOLATED_MOCK_V1',MOCK_INIT_OBJECT_ID:id,MOCK_INIT_TOKEN:control});
      assert.equal((await mf.dispatchFetch('https://stage1.invalid/_mock/initialize',{method:'POST',headers:{Authorization:'Bearer '+control},body:'{}'})).status,403);
      await assert.rejects(()=>stub.initializeIsolatedMock({},control));await reset(bindings);
    });
    await check('repeated identity then process runtime restart retains identity and emptiness',async()=>{
      for(let i=0;i<3;i++)assert.deepEqual(await readIdentity(),expected);
      await mf.dispose();mf=new Miniflare(options(bindings));await mf.ready;stub=(await mf.getDurableObjectNamespace('COORDINATOR')).getByName(OBJECT_NAME);
      assert.deepEqual(await readIdentity(),expected);
    });
    writeTestResult(full?'stage1_full_output_workerd_results.json':'stage1_workerd_results.json',{status:'PASS',checks:count,
      environment:full?'LOCAL_WORKERD_ACTUAL_CF_BUILD_OUTPUT':'LOCAL_WORKERD_SQLITE_WITH_TEST_ONLY_OBSERVER',
      sql_and_native_empty:true,receipt_absent:true,alarm:null,collector_calls:0,outbound_requests:outbound,
      snapshot:full?expected:await inspect(),runtime_restart_same_id:true,credentials:'RANDOM_TEST_PROCESS_ONLY_NOT_RECORDED'});
  }finally{await mf.dispose();}
});
