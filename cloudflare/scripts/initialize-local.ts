import {randomBytes,randomUUID} from 'node:crypto';
import {makeLocalInitializationHarness} from './local-runtime.ts';

// Deliberately no URL/account/namespace command-line options and no remote mode.
if(process.argv[2]!=='--local')throw Error('EXPLICIT_LOCAL_MODE_REQUIRED');
const credential=randomBytes(32).toString('hex');let outbound=0;
const {mf,stub,objectId}=await makeLocalInitializationHarness(credential,()=>{outbound++;});
try {
  const result=await stub.initializeIsolatedMock({operation:'INITIALIZE_EMPTY_ISOLATED_MOCK',target_object_id:objectId,
    request_id:randomUUID(),operator:'LOCAL_INITIALIZATION_TOOL',authorization_reference:'PHASE_5_1A_OFFLINE_ONLY',reason:'Explicit local initialization rehearsal'},credential);
  console.log(JSON.stringify({mode:'LOCAL_ONLY',receipt_id:result.receipt_id,initialized_at_utc:result.initialized_at_utc,outbound_requests:outbound}));
}finally{await mf.dispose();}
