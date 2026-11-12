// Local-only workerd harness shared by the H01 tool and security runtime tests.
// It has no remote binding, deployment or credential discovery code.
import {Miniflare, MiniflareOptions} from 'miniflare';
import {readFileSync,mkdtempSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import type {InitializationPolicy} from '../src/initialization.ts';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
export function localRuntimeOptions(persistence:string, policy:InitializationPolicy={},testing=false,onOutbound=()=>{}):MiniflareOptions {
  return {host:'127.0.0.1',port:0,cf:false,telemetry:{enabled:false},enableDevRegistry:false,
    resourcePersistencePath:persistence,resourceTmpPath:resolve(root,'.tmp'),
    workers:[{config:{name:'hardening-local',compatibilityDate:'2026-11-10',compatibilityFlags:['nodejs_compat'],
      manifest:{mainModule:'worker.js',modulesRoot:resolve(root,'dist'),modules:{'worker.js':{type:'esm',contents:readFileSync(resolve(root,'dist/worker.js'),'utf8')}}},
      exports:{ExecutionCoordinator:{type:'durable-object',storage:'sqlite'}},
      env:{COORDINATOR:{type:'durable-object',worker:'hardening-local',exportName:'ExecutionCoordinator'},
        REPORT_TOKEN:{type:'text',value:'LOCAL_REPORT_FIXTURE_ONLY'},
        ...(testing?{LOCAL_TESTING:{type:'text' as const,value:'1'}}:{}),
        ...Object.fromEntries(Object.entries(policy).map(([key,value])=>[key,{type:'text' as const,value:value!}]))}
    },dev:{outboundService:{type:'fetcher',handler:()=>{onOutbound();throw Error('EXTERNAL_NETWORK_FORBIDDEN');}}}}]};
}
export function newLocalPersistence() {mkdirSync(resolve(root,'.tmp'),{recursive:true});return mkdtempSync(resolve(root,'.tmp/initialization-'));}
export async function makeLocalInitializationHarness(credential:string,onOutbound=()=>{}) {
  const path=newLocalPersistence(),mf=new Miniflare(localRuntimeOptions(path,{},false,onOutbound));await mf.ready;
  const objectId=(await mf.getDurableObjectNamespace('COORDINATOR')).idFromName('fixed-us-stocks-poc-v1').toString();
  await mf.setOptions(localRuntimeOptions(path,{MOCK_INIT_ENABLED:'EXPLICIT_ISOLATED_MOCK_V1',MOCK_INIT_TOKEN:credential,MOCK_INIT_OBJECT_ID:objectId},false,onOutbound));
  const stub:any=(await mf.getDurableObjectNamespace('COORDINATOR')).getByName('fixed-us-stocks-poc-v1');
  return {mf,stub,objectId};
}
