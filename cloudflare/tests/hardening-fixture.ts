import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,copyFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {Store,canonical,digest,register,reportAsset} from '../src/storage.ts';
import {Coordinator} from '../src/coordinator.ts';
import {MockYahoo} from '../src/mock.ts';
import {stableId,calendar,RecordValue as R} from '../src/core.ts';

export const DATE='2026-11-06',TIME=Date.parse('2026-11-07T00:00:00Z');
export const NEXT='2026-11-09',NEXT_TIME=Date.parse('2026-11-10T00:00:00Z');
export const temporary=()=>mkdtempSync(resolve('.tmp/hardening-'));
export function connection(path=':memory:') {
  const db=new DatabaseSync(path);
  const store=new Store({sql:{exec(sql,...args) {const rows=db.prepare(sql).all(...args);return {toArray:()=>rows};}},
    transactionSync(fn) {db.exec('BEGIN IMMEDIATE');try{const value=fn();db.exec('COMMIT');return value;}catch(error){db.exec('ROLLBACK');throw error;}}});
  return {db,store};
}
export async function finish(engine:Coordinator,date=DATE,time=TIME) {
  for(let i=0;i<20;i++)if(await engine.tick(date,time+i*35000)==='COMPLETE')return;
  throw Error('Mock run did not complete');
}
export function nextCollector() {
  const mock=new MockYahoo();return {calls:[] as string[],async collect(symbol:string) {
    this.calls.push(symbol);const response=await mock.collect(symbol),raw=JSON.parse(response.raw),r=raw.chart.result[0];
    r.timestamp.push(calendar[NEXT]![0]/1000);
    for(const field of ['adjclose','close']){const values=field==='adjclose'?r.indicators.adjclose[0].adjclose:r.indicators.quote[0].close;values.push(values.at(-1)*0.99);}
    return {status:200,raw:JSON.stringify(raw),asof:new Date(NEXT_TIME).toISOString()};
  }};
}
export function replaceState(store:Store,symbol:string,fn:(doc:R)=>void) {
  const row=store.q('SELECT * FROM states WHERE symbol=?',symbol)[0],doc=JSON.parse(row.body);fn(doc);
  const body=canonical(doc);store.q('UPDATE states SET body=?,hash=? WHERE symbol=?',body,digest(`${row.version}:${body}`),symbol);
  const report=canonical(reportAsset(doc));store.q('UPDATE history SET body=?,hash=? WHERE symbol=? AND version=?',report,digest(`${row.version}:${report}`),symbol,row.version);
}
export function replaceEvent(store:Store,id:string,fn:(event:R)=>void) {
  const row=store.q('SELECT * FROM events WHERE id=?',id)[0],event=JSON.parse(row.body);fn(event);
  const body=canonical(event);store.q('UPDATE events SET body=?,hash=? WHERE id=?',body,digest(body),id);
}
export async function seedNativeEvents(store:Store) {
  const ids:R={};
  for(const symbol of ['NVDA','^GSPC']) {
    const index=symbol.startsWith('^'),ledger:R={};
    const crossing={symbol,trading_date:DATE,event_type:'THRESHOLD_CROSSING',event_subtype:'NEW_THRESHOLD',threshold:20,status:'CONFIRMED',evidence:{fixture:'synthetic structural checkpoint'}};
    const confirmed=await stableId(crossing,index);register(ledger,confirmed,crossing,index);
    const candidate={...crossing,threshold:30,status:'PENDING_REVIEW'};const pending=await stableId(candidate,index);register(ledger,pending,candidate,index);
    const revision={symbol,trading_date:DATE,event_type:'REVISION_OBSERVATION',threshold:null,status:'CONFIRMED',evidence:{revision_observation:{requires_review:false}}};
    const revisionId=await stableId(revision,index);register(ledger,revisionId,revision,index);
    register(ledger,revisionId,{...revision,status:'PENDING_REVIEW',evidence:{revision_observation:{requires_review:true}}},index);
    const rejected={symbol,trading_date:DATE,event_type:'RECOVERY',threshold:null,status:'REJECTED',evidence:{fixture:'explicit terminal structural fixture'}};
    const rejectedId=await stableId(rejected,index);register(ledger,rejectedId,rejected,index);
    for(const [id,event] of Object.entries(ledger)){const body=canonical(event);store.q('INSERT INTO events VALUES (?,?,?,?)',index?'indices':'stocks',id,body,digest(body));}
    replaceState(store,symbol,doc=>{doc.confirmed_thresholds=[20];doc.triggered_thresholds=[20];doc.threshold_state.confirmed=[20];doc.threshold_state.pending_event_ids=[pending,revisionId].sort();doc.revision_review_event_ids=[revisionId];});
    ids[symbol]={confirmed,pending,revision:revisionId,rejected:rejectedId};
  }
  return ids;
}
let cached:Promise<{path:string;ids:R}>|undefined;
export function fixture() {
  cached??=(async()=> {
    const path=resolve(temporary(),'baseline.sqlite'),{db,store}=connection(path);store.initialize();
    const engine=new Coordinator(store,new MockYahoo());engine.start(DATE,TIME);await finish(engine);
    const ids=await seedNativeEvents(store);store.validateFullCheckpoint();db.close();return {path,ids};
  })();return cached;
}
export async function copyFixture() {
  const base=await fixture(),path=resolve(temporary(),'copy.sqlite');copyFileSync(base.path,path);
  return {...connection(path),ids:base.ids};
}
export function snapshot(store:Store) {
  const tables=store.q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*' ORDER BY name");
  return canonical(Object.fromEntries(tables.map(t=>[t.name,store.q(`SELECT * FROM "${t.name}"`)])));
}
