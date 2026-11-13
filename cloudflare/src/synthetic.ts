import {calendar,INDICES,SYMBOLS} from './core.ts';
import type {Collector} from './coordinator.ts';

// Invented prices, not archived Yahoo responses or historical PIT observations.
export const FIXTURE_DATES=['2026-11-06','2026-11-09'] as const;
const names=['NVIDIA Corporation','Apple Inc','Alphabet Inc','Microsoft Corporation','Amazon.com Inc','SpaceX','Meta Platforms Inc','Broadcom Inc','Tesla Inc','S&P 500','NASDAQ 100','PHLX Semiconductor'];
export class SyntheticCollector implements Collector {
  calls:string[]=[];
  async collect(symbol:string,date?:string) {
    if(!FIXTURE_DATES.includes(date as any)||!SYMBOLS.includes(symbol))throw Error('MOCK_FIXTURE_NOT_ALLOWED');
    this.calls.push(symbol);
    const index=INDICES.includes(symbol),i=SYMBOLS.indexOf(symbol);
    // A common starting date preserves every old invented bar in fixture two.
    const all=Object.keys(calendar).sort().filter(d=>calendar[d]&&d>='2025-10-01'&&d<=date!&&(symbol!=='SPCX'||d>='2026-06-12'));
    const values=all.map((_,j)=>symbol==='^SOX'?200-j*0.25:100+i*7+j*0.025+Math.sin(j/5));
    const meta={symbol,instrumentType:index?'INDEX':'EQUITY',currency:'USD',exchangeTimezoneName:'America/New_York',
      exchangeName:index?(symbol==='^GSPC'?'SNP':'NIM'):'NMS',fullExchangeName:index?(symbol==='^GSPC'?'SNP':'Nasdaq GIDS'):'NasdaqGS',longName:names[i],
      synthetic:true,provenance:'MOCK_ONLY_SYNTHETIC_V1',...(symbol==='SPCX'?{firstTradeDate:calendar['2026-06-12']![0]/1000}:{})};
    return {status:200,asof:new Date(calendar[date!]![1]+1000).toISOString(),raw:JSON.stringify({chart:{error:null,result:[{meta,
      timestamp:all.map(d=>calendar[d]![0]/1000),indicators:{adjclose:[{adjclose:values}],quote:[{close:values}]} }]}})};
  }
}
