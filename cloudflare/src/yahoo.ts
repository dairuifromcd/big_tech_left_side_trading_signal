import {calendar,latestSession,nyDate,positive,validateSeries,STOCKS,INDICES,RecordValue,Pair} from './core.ts';
const aliases:Record<string,string[]>={NVDA:['NVIDIA Corporation','NVIDIA Corp'],AAPL:['Apple Inc'],GOOGL:['Alphabet Inc'],MSFT:['Microsoft Corporation','Microsoft Corp'],AMZN:['Amazon.com Inc'],SPCX:['Space Exploration Technologies Corp','Space Exploration Technologies Corporation','SpaceX'],META:['Meta Platforms Inc'],AVGO:['Broadcom Inc'],TSLA:['Tesla Inc']};
const indexNames:Record<string,string[]>={'^GSPC':['S&P 500'],'^NDX':['NASDAQ 100','NASDAQ-100'],'^SOX':['PHLX Semiconductor','PHLX Semiconductor Sector']};
const venues:Record<string,string[]>={'^GSPC':['SNP','SNP'],'^NDX':['NIM','Nasdaq GIDS'],'^SOX':['NIM','Nasdaq GIDS']};
const normalize=(s:string)=>String(s??'').toLowerCase().replace(/\b(class\s+a|common stock|ordinary shares)\b/g,'').replace(/[^a-z0-9]/g,'');
export function validateIdentity(symbol:string,m:RecordValue) {
  const index=INDICES.includes(symbol);
  let valid=m?.symbol===symbol && m?.instrumentType===(index?'INDEX':'EQUITY') && m?.currency==='USD' && m?.exchangeTimezoneName==='America/New_York';
  if(index)valid=valid && venues[symbol][0]===m.exchangeName && venues[symbol][1]===m.fullExchangeName && indexNames[symbol].includes(m.longName||m.shortName);
  else valid=valid && STOCKS.includes(symbol) && m.exchangeName==='NMS' && ['NasdaqGS','Nasdaq Global Select Market','NASDAQ Global Select Market'].includes(m.fullExchangeName) && aliases[symbol].map(normalize).includes(normalize(m.longName||m.shortName));
  if(symbol==='SPCX' && m?.firstTradeDate!=null)valid=valid && typeof m.firstTradeDate==='number' && nyDate(m.firstTradeDate*1000)==='2026-06-12';
  if(!valid)throw Error('IDENTITY_MISMATCH');
}
export function sameIdentity(symbol:string,a:RecordValue,b:RecordValue) {
  try {validateIdentity(symbol,a);validateIdentity(symbol,b);}catch{return false;}
  return ['symbol','instrumentType','currency','exchangeName','fullExchangeName','exchangeTimezoneName'].every(k=>a[k]===b[k]);
}
export interface Sample {symbol:string; pairs:Pair[]; closes:Record<string,number>; identity:RecordValue; target:string; as_of_utc:string; excluded_incomplete_dates:string[]; data_quality:string}
export function validateYahoo(symbol:string,payload:RecordValue,asof:string):Sample {
  if(![...STOCKS,...INDICES].includes(symbol))throw Error('UNKNOWN_SYMBOL');
  const chart=payload?.chart;
  if(!chart||chart.error||!Array.isArray(chart.result)||chart.result.length!==1)throw Error('DATA_QUALITY_ERROR');
  const result=chart.result[0],meta=result?.meta;validateIdentity(symbol,meta);
  const adj=result?.indicators?.adjclose?.[0]?.adjclose,cl=result?.indicators?.quote?.[0]?.close,stamps=result?.timestamp;
  if(!Array.isArray(adj)||!adj.length)throw Error('MISSING_ADJCLOSE');
  if(!Array.isArray(cl)||!Array.isArray(stamps)||cl.length!==stamps.length||adj.length!==stamps.length)throw Error('DATA_QUALITY_ERROR');
  const target=latestSession(asof),now=Date.parse(asof),pairs:Pair[]=[],closes:Record<string,number>={},excluded:string[]=[],seen=new Set();
  for(let i=0;i<stamps.length;i++) {
    if(typeof stamps[i]!=='number'||!Number.isFinite(stamps[i]))throw Error('DATA_QUALITY_ERROR');
    const ms=stamps[i]*1000,d=nyDate(ms),bounds=calendar[d];
    if(!bounds||ms<bounds[0]||ms>bounds[1]||seen.has(d))throw Error('DATA_QUALITY_ERROR');seen.add(d);
    if(symbol==='SPCX'&&d<'2026-06-12')throw Error('DATA_QUALITY_ERROR: PRE_IPO');
    // The equity collector rejects invalid unfinished prices; index adapter excludes them first.
    if(!INDICES.includes(symbol)&&(!positive(adj[i])||!positive(cl[i])))throw Error('DATA_QUALITY_ERROR');
    if(now<bounds[1]) {excluded.push(d);continue;}
    if(!positive(adj[i])||!positive(cl[i]))throw Error('DATA_QUALITY_ERROR');
    pairs.push([d,adj[i]]);closes[d]=cl[i];
  }
  validateSeries(pairs,target);
  if(pairs.length<252 && !(symbol==='SPCX'&&pairs[0][0]==='2026-06-12'))throw Error('INSUFFICIENT_HISTORY');
  return {symbol,pairs,closes,identity:meta,target,as_of_utc:asof,excluded_incomplete_dates:excluded,data_quality:symbol==='SPCX'?'PASS_PROVISIONAL':'PASS'};
}
