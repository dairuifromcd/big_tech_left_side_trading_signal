// Local test artifact only: not referenced by either deployment entrypoint.
import {DurableObject} from 'cloudflare:workers';
import {Store} from '../src/storage.ts';
import {exerciseStart,StartCase} from './mock-start-atomicity-fixture.ts';
export class AtomicityTest extends DurableObject {
  exercise(scenario:StartCase) {return exerciseStart(new Store(this.ctx.storage,undefined,'MOCK_ONLY_SYNTHETIC_V1'),scenario);}
}
export default {fetch(){return new Response('LOCAL_TEST_ONLY',{status:403});}};
