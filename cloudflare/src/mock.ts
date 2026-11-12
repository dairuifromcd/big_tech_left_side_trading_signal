import samples from '../fixtures/samples.json';
import {calendar} from './core.ts';
import type {Collector} from './coordinator.ts';
// There is intentionally no Yahoo network transport in this PoC.
export class MockYahoo implements Collector {
  calls:string[]=[];
  constructor(readonly status=200,readonly failSymbol?:string) {}
  async collect(symbol:string) {
    this.calls.push(symbol);const s=samples.find(s=>s.symbol===symbol)!;
    const raw={chart:{error:null,result:[{
      meta:s.identity,
      timestamp:s.pairs.map(([d])=>calendar[d as string]![0]/1000),
      indicators:{
        adjclose:[{adjclose:s.pairs.map(p=>p[1])}],
        quote:[{close:s.pairs.map(([d])=>(s.closes as any)[d])}]
      }
    }]}};
    return {status:symbol===this.failSymbol?this.status:200,raw:JSON.stringify(raw),asof:s.as_of_utc};
  }
}
