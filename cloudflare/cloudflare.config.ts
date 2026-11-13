import {bindings,defineConfig,exports} from 'cf/config';
// Path entrypoints prevent the local archived-fixture module entering the remote
// build graph. The explicitly selected remote mode is disabled until Gate B.
export default defineConfig(({mode})=>['p51b-mock','p51b-identity-prep'].includes(mode)?{worker:{
  name:'us-stocks-p51b-mock-20261113',entrypoint:'./src/remote-worker.ts',
  compatibilityDate:'2026-11-10',compatibilityFlags:['nodejs_compat'],
  exports:{RemoteMockCoordinator:exports.durableObject({storage:'sqlite'})},
  env:{COORDINATOR:bindings.durableObject({worker:'us-stocks-p51b-mock-20261113',exportName:'RemoteMockCoordinator'}),
    REMOTE_MOCK_ENABLED:bindings.text('DISABLED_PENDING_GATE_B'),
    MOCK_START_UTC:bindings.text(mode==='p51b-identity-prep'?'2026-11-15T22:00:00Z':'2026-11-15T23:00:00Z'),
    MOCK_END_UTC:bindings.text(mode==='p51b-identity-prep'?'2026-11-16T22:00:00Z':'2026-11-16T23:00:00Z'),
    MOCK_INIT_END_UTC:bindings.text(mode==='p51b-identity-prep'?'2026-11-15T22:20:00Z':'2026-11-15T23:20:00Z')}
}}:{worker:{
  name:'us-stocks-phase51-offline',
  entrypoint:'./src/worker.ts',
  compatibilityDate:'2026-11-10',
  compatibilityFlags:['nodejs_compat'],
  exports:{ExecutionCoordinator:exports.durableObject({storage:'sqlite'})},
  env:{COORDINATOR:bindings.durableObject({worker:'us-stocks-phase51-offline',exportName:'ExecutionCoordinator'})}
}});
