import {bindings,defineConfig,exports} from 'cf/config';
import * as entrypoint from './src/worker.ts' with {type:'cf-worker'};
// Local PoC only. No account ID, secrets, route, asset binding or Cron provisioned.
export default defineConfig({worker:{
  name:'us-stocks-phase51-offline',
  entrypoint,
  compatibilityDate:'2026-11-10',
  compatibilityFlags:['nodejs_compat'],
  exports:{ExecutionCoordinator:exports.durableObject({storage:'sqlite'})},
  env:{COORDINATOR:bindings.durableObject({worker:'us-stocks-phase51-offline',exportName:'ExecutionCoordinator'})}
}});
