// Reproducible, credential-free local commands. No deployment command exists.
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {mkdirSync} from 'node:fs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const node=resolve(root,'node_modules/node/bin/node');
const env={PATH:resolve(root,'node_modules/node/bin')+':'+resolve(root,'node_modules/.bin')+':/usr/bin:/bin',TMPDIR:resolve(root,'.tmp'),XDG_CACHE_HOME:resolve(root,'.cache'),XDG_CONFIG_HOME:resolve(root,'.home'),CF_SEND_TELEMETRY:'0',CI:'true',NO_UPDATE_NOTIFIER:'1'};
for(const p of [env.TMPDIR,env.XDG_CACHE_HOME,env.XDG_CONFIG_HOME])mkdirSync(p,{recursive:true});
const commands={
  build:[node,[resolve(root,'node_modules/cf/bin/cf'),'build']],
  typecheck:[node,[resolve(root,'node_modules/typescript/bin/tsc'),'--noEmit']],
  test:[node,['--import','tsx','--test','tests/parity.test.ts','tests/storage.test.ts','tests/runtime.test.ts']],
  offline:[node,['--import','tsx','--test','tests/parity.test.ts','tests/storage.test.ts']],
};
const selected=commands[process.argv[2]];
if(!selected)throw Error('Choose build, typecheck, test, or offline. Remote commands are not exposed.');
if(process.argv[2]==='test') {
  const built=spawnSync(resolve(root,'node_modules/.bin/esbuild'),['src/worker.ts','--bundle','--format=esm','--platform=neutral','--external:cloudflare:workers','--external:node:crypto','--outfile=dist/worker.js'],{cwd:root,env,stdio:'inherit'});if(built.status!==0)process.exit(built.status??1);
}
const result=spawnSync(selected[0],selected[1],{cwd:root,env,stdio:'inherit'});process.exit(result.status??1);
