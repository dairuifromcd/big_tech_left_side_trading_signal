// Reproducible, credential-free local commands. No deployment command exists.
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {mkdirSync} from 'node:fs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const node=resolve(root,'node_modules/node/bin/node');
const env={PATH:resolve(root,'node_modules/node/bin')+':'+resolve(root,'node_modules/.bin')+':/usr/bin:/bin',TMPDIR:resolve(root,'.tmp'),XDG_CACHE_HOME:resolve(root,'.cache'),XDG_CONFIG_HOME:resolve(root,'.home'),CF_SEND_TELEMETRY:'0',CI:'true',NO_UPDATE_NOTIFIER:'1'};
const results=process.argv[3];
if(results) {
  const path=resolve(root,'..',results),project=resolve(root,'..');
  if(!path.startsWith(project+'/')||path.startsWith(resolve(project,'phase5_1_cloudflare_free')+'/')||path===resolve(project,'phase5_1_cloudflare_free'))throw Error('NEW_PROJECT_LOCAL_RESULTS_REQUIRED');
  env.POC_RESULTS_DIR=path;
}
for(const p of [env.TMPDIR,env.XDG_CACHE_HOME,env.XDG_CONFIG_HOME])mkdirSync(p,{recursive:true});
const commands={
  build:[node,[resolve(root,'node_modules/cf/bin/cf'),'build']],
  typecheck:[node,[resolve(root,'node_modules/typescript/bin/tsc'),'--noEmit']],
  test:[node,['--import','tsx','--test','tests/parity.test.ts','tests/storage.test.ts','tests/runtime.test.ts','tests/hardening.test.ts','tests/hardening-runtime.test.ts','tests/remote-mock.test.ts','tests/remote-mock-runtime.test.ts','tests/stage1.test.ts','tests/stage1-runtime.test.ts']],
  offline:[node,['--import','tsx','--test','tests/parity.test.ts','tests/storage.test.ts','tests/hardening.test.ts']],
  'initialize-local':[node,['--import','tsx','scripts/initialize-local.ts','--local']],
  'remote-unit':[node,['--import','tsx','--test','tests/remote-mock.test.ts']],
  'remote-dry-run':[node,[resolve(root,'node_modules/cf/bin/cf'),'deploy','--mode','p51b-mock','--dry-run','--provision=false']],
  'remote-preparation-dry-run':[node,[resolve(root,'node_modules/cf/bin/cf'),'deploy','--mode','p51b-identity-prep','--dry-run','--provision=false']],
  'stage1-build':[node,[resolve(root,'node_modules/cf/bin/cf'),'build','--mode','p51b-stage1']],
  'stage1-dry-run':[node,[resolve(root,'node_modules/cf/bin/cf'),'deploy','--mode','p51b-stage1','--dry-run','--provision=false']],
  'stage1-prebuilt-dry-run':[node,[resolve(root,'node_modules/cf/bin/cf'),'deploy','--prebuilt','--mode','p51b-stage1','--dry-run','--provision=false']],
  'stage1-packaged-dry-run':[node,[resolve(root,'node_modules/cf/bin/cf'),'deploy','--prebuilt','--mode','p51b-stage1','--dry-run','--provision=false']],
  'stage1-full-output-test':[node,['--import','tsx','--test','tests/stage1-runtime.test.ts']],
};
const selected=commands[process.argv[2]];
if(process.argv[2]==='stage1-full-output-test')env.STAGE1_FULL_OUTPUT='1';
if(!selected)throw Error('Choose build, typecheck, test, offline, or initialize-local. Remote commands are not exposed.');
if(process.argv[2]==='test') {
  const built=spawnSync(resolve(root,'node_modules/.bin/esbuild'),['src/worker.ts','--bundle','--format=esm','--platform=neutral','--external:cloudflare:workers','--external:node:crypto','--outfile=dist/worker.js'],{cwd:root,env,stdio:'inherit'});if(built.status!==0)process.exit(built.status??1);
  const remote=spawnSync(resolve(root,'node_modules/.bin/esbuild'),['src/remote-worker.ts','--bundle','--format=esm','--platform=neutral','--external:cloudflare:workers','--external:node:crypto','--metafile=dist/remote-meta.json','--outfile=dist/remote-worker.js'],{cwd:root,env,stdio:'inherit'});if(remote.status!==0)process.exit(remote.status??1);
}
const cwd=process.argv[2]==='stage1-packaged-dry-run'?resolve(root,'../phase5_1b_cloudflare_remote_mock/stage1_local_package/builds/stage1'):root;
const result=spawnSync(selected[0],selected[1],{cwd,env,stdio:'inherit'});process.exit(result.status??1);
