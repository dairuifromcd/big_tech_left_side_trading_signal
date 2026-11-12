import {mkdirSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, relative, isAbsolute} from 'node:path';

const project=resolve(fileURLToPath(new URL('../../',import.meta.url)));
export function writeTestResult(name:string, value:any) {
  const output=resolve(process.env.POC_RESULTS_DIR??resolve(project,'cloudflare/.tmp/results'));
  const path=relative(project,output);
  if(path.startsWith('..')||isAbsolute(path)||!path||name.includes('/')||name.includes('\\'))throw Error('PROJECT_LOCAL_RESULTS_REQUIRED');
  // Historical acceptance files are immutable; callers must choose new results.
  if(path.split(/[\\/]/)[0]==='phase5_1_cloudflare_free')throw Error('HISTORICAL_RESULTS_ARE_READ_ONLY');
  mkdirSync(output,{recursive:true});writeFileSync(resolve(output,name),JSON.stringify(value,null,2)+'\n');
}
