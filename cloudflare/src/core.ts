// Reference: src/indicators.py, src/signals.py. No display rounding here.
import schedule from './calendar-data.json';
export type RecordValue = Record<string, any>;
export type Pair = [string, number];
export const RULES = 'adjclose-wilder14-sma-252-v1';
export const STOCKS = ['NVDA','AAPL','GOOGL','MSFT','AMZN','SPCX','META','AVGO','TSLA'];
export const INDICES = ['^GSPC','^NDX','^SOX'];
export const SYMBOLS = [...STOCKS,...INDICES];
export const calendar = schedule as unknown as Record<string, [number, number] | null>;
export function checkDate(d: string) {
  if (!Object.hasOwn(calendar,d)) throw Error('CALENDAR_OUT_OF_RANGE_OR_INVALID');
}
export function sessions(start: string,end: string) {
  checkDate(start); checkDate(end);
  return Object.keys(calendar).filter(d=>d>=start && d<=end && calendar[d]);
}
export function nyDate(ms: number) {
  if (!Number.isFinite(ms) || !Number.isFinite(new Date(ms).getTime())) throw Error('INVALID_TIMESTAMP');
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(ms);
  const get=(k:string)=>parts.find(p=>p.type===k)!.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
export function latestSession(asof: string | number) {
  if (typeof asof==='string' && !/(Z|[+-]\d\d:\d\d)$/.test(asof)) throw Error('AWARE_TIME_REQUIRED');
  const ms=typeof asof==='number'?asof:Date.parse(asof); const d=nyDate(ms);checkDate(d);
  const found=Object.keys(calendar).filter(x=>x<=d && calendar[x] && calendar[x]![1]<=ms).at(-1);
  if (!found) throw Error('NO_COMPLETED_SESSION');return found;
}
export function missing(previous: string,target: string) {return target<=previous?[]:sessions(previous,target).slice(1,-1);}
export const positive=(v:unknown):v is number=>typeof v==='number' && Number.isFinite(v) && v>0;
export function validateSeries(rows:Pair[], target:string) {
  if (!rows.length || rows.at(-1)![0]!==target) throw Error('STALE_DATA');
  const expected=sessions(rows[0][0],target);
  if (expected.length!==rows.length || rows.some(([d,p],i)=>d!==expected[i] || !positive(p))) throw Error('DATA_QUALITY_ERROR');
}
// Non-overlapping partial sums, following the compensated fsum algorithm.
export function fsum(values:number[]) {
  const partials:number[]=[];
  for (let x of values) {
    let i=0;
    for (let y of partials) {
      if(Math.abs(x)<Math.abs(y)) [x,y]=[y,x];
      const hi=x+y,lo=y-(hi-x);if(lo) partials[i++]=lo;x=hi;
    }
    partials.length=i;partials.push(x);
  }
  let n=partials.length,hi=0,lo=0;
  if(n) {hi=partials[--n];while(n) {const x=hi,y=partials[--n];hi=x+y;lo=y-(hi-x);if(lo)break;}
    if(n && ((lo<0 && partials[n-1]<0)||(lo>0 && partials[n-1]>0))) {const y=lo*2,x=hi+y;if(y===x-hi)hi=x;}}
  return hi;
}
export function rsi(prices:number[],period=14) {
  if(prices.length<period+1)return null;
  const changes=prices.slice(1).map((p,i)=>p-prices[i]);
  let gain=fsum(changes.slice(0,period).map(c=>Math.max(c,0)))/period;
  let loss=fsum(changes.slice(0,period).map(c=>Math.max(-c,0)))/period;
  for(const c of changes.slice(period)) {gain=(gain*(period-1)+Math.max(c,0))/period;loss=(loss*(period-1)+Math.max(-c,0))/period;}
  return gain===0&&loss===0?50:loss===0?100:100-100/(1+gain/loss);
}
export function calculate(rows:Pair[],target:string,short=false):RecordValue {
  validateSeries(rows,target);if(rows.length<252&&!short)throw Error('INSUFFICIENT_HISTORY');
  const window=rows.slice(-252);let high=window[0];for(const p of window)if(p[1]>=high[1])high=p;
  const prices=rows.map(p=>p[1]),last=prices.at(-1)!;
  const result:RecordValue={trading_date:target,adjclose:last,window_samples:window.length,highest_adjclose:high[1],highest_date:high[0],drawdown:last/high[1]-1,rsi14:rsi(prices),sma50:prices.length>=50?fsum(prices.slice(-50))/50:null,sma200:prices.length>=200?fsum(prices.slice(-200))/200:null,rsi_warmup_prices:prices.length,high_tie_rule:'LATEST_DATE_EXACT_EQUAL_PRICE'};
  result.indicator_status=Object.fromEntries(['drawdown','rsi14','sma50','sma200'].map(k=>[k,result[k]===null?'INSUFFICIENT_HISTORY':'VALID']));return result;
}
export const crossed=(dd:number)=>[10,20,30].filter(n=>dd*100<=-n+1e-10);
export const tier=(dd:number)=>crossed(dd).length?`WATCH_${crossed(dd).at(-1)}`:'NONE';
export const unique=(v:number[])=>[...new Set(v)].sort((a,b)=>a-b);
export const equal=(a:any,b:any):boolean=>JSON.stringify(sorted(a))===JSON.stringify(sorted(b));
export function sorted(x:any):any {return Array.isArray(x)?x.map(sorted):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sorted(x[k])])):x;}
export function transition(previous:RecordValue|null,current:RecordValue,significant=1):RecordValue {
  if(!positive(significant))throw Error('INVALID_SIGNIFICANT_PP');
  const now=crossed(current.drawdown),old=previous?crossed(previous.drawdown):[],touched:number[]=previous?.triggered_thresholds??[];
  let entering=now.filter(x=>!old.includes(x)),event:string;
  if(!previous){event='FIRST_BASELINE';entering=[];}
  else if(current.trading_date===previous.trading_date){event='NO_CHANGE';entering=[];}
  else if(entering.length)event=entering.some(x=>!touched.includes(x))?'NEW_THRESHOLD':'REENTRY';
  else if(now.length<old.length)event='RECOVERY';
  else if(now.length&&((previous.deepening_anchor??previous.drawdown)-current.drawdown)*100>=significant-1e-10)event='DEEPER_DRAWDOWN';
  else event='NO_CHANGE';
  const fresh=entering.filter(x=>!touched.includes(x));
  return {change_event:event,watch_tier:tier(current.drawdown),previous_watch_tier:previous?.watch_tier??null,crossed_thresholds_this_run:entering,new_thresholds:fresh,reentered_thresholds:entering.filter(x=>touched.includes(x)),triggered_thresholds:unique([...touched,...now]),last_new_trigger_date:fresh.length?current.trading_date:previous?.last_new_trigger_date??null,deepening_anchor:event!=='NO_CHANGE'?current.drawdown:previous?.deepening_anchor??previous?.drawdown};
}
export const closeEnough=(a:number,b:number,abs=1e-8,rel=1e-10)=>Math.abs(a-b)<=Math.max(abs,rel*Math.abs(a),rel*Math.abs(b));
export function revisions(previous:RecordValue|null,prices:Record<string,number>) {
  if(!previous)return [];const dates=Object.keys(previous.history_prices).filter(d=>Object.hasOwn(prices,d)).sort();
  if(!dates.length)throw Error('NO_OVERLAPPING_HISTORY');
  return dates.filter(d=>!closeEnough(previous.history_prices[d],prices[d])).map(d=>({date:d,previous:previous.history_prices[d],current:prices[d]}));
}
// Semantic IDs use only strings, integer thresholds and null. Python json.dumps
// separators and ensure_ascii are reproduced explicitly; float evidence uses v1 JS canonical hashing separately.
export function semanticJson(v:any):string {
  if(v===null)return 'null';if(Array.isArray(v))return '['+v.map(semanticJson).join(', ')+']';
  if(typeof v==='object')return '{'+Object.keys(v).sort().map(k=>semanticJson(k)+': '+semanticJson(v[k])).join(', ')+'}';
  if(typeof v==='number'&&!Number.isFinite(v))throw Error('NON_FINITE');
  return JSON.stringify(v).replace(/[\u007f-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
}
export async function sha(text:string) {return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))].map(x=>x.toString(16).padStart(2,'0')).join('');}
export function eventSemantic(e:RecordValue,index=false) {
  if(!(index?INDICES:STOCKS).includes(e.symbol)||!e.event_type||![null,10,20,30].includes(e.threshold??null))throw Error('EVENT_SCHEMA_ERROR');
  checkDate(e.trading_date);
  const semantic:RecordValue={symbol:e.symbol,trading_date:e.trading_date,event_type:e.event_type,threshold:e.threshold??null,rules_version:e.rules_version??RULES,event_model_version:e.event_model_version??(index?'indices-revision-market-v2':'revision-market-v2')};
  if(semantic.rules_version!==RULES||semantic.event_model_version!==(index?'indices-revision-market-v2':'revision-market-v2'))throw Error('EVENT_SCHEMA_ERROR');
  if(index)semantic.category='Market Indices';return semantic;
}
export async function stableId(e:RecordValue,index=false) {
  return sha(semanticJson(eventSemantic(e,index)));
}
