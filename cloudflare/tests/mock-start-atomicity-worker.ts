// Local test artifact only: not referenced by either deployment entrypoint.
import {DurableObject} from 'cloudflare:workers';
import {Store} from '../src/storage.ts';
import {exerciseStart,exerciseAdvancedDuplicate,StartCase} from './mock-start-atomicity-fixture.ts';
export class AtomicityTest extends DurableObject {
  async duplicateAfterAdvance(withEvents:boolean) {
    const before=await this.ctx.storage.getAlarm();
    const result=exerciseAdvancedDuplicate(new Store(this.ctx.storage,undefined,'MOCK_ONLY_SYNTHETIC_V1'),withEvents);
    const after=await this.ctx.storage.getAlarm();
    if(before!==null||after!==before)throw Error('UNEXPECTED_ALARM');
    return {...result,alarm_before:before,alarm_after:after};
  }
  exercise(scenario:StartCase) {return exerciseStart(new Store(this.ctx.storage,undefined,'MOCK_ONLY_SYNTHETIC_V1'),scenario);}
}
export default {fetch(){return new Response('LOCAL_TEST_ONLY',{status:403});}};
