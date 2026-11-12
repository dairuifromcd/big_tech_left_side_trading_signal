import {RecordValue as R,SYMBOLS,INDICES,RULES,calendar,missing,stableId,unique,latestSession} from './core.ts';
import {Store,register,digest,canonical,pythonPriceFingerprint} from './storage.ts';
import {validateYahoo} from './yahoo.ts';
import {evaluate} from './observations.ts';
export interface Collector {collect(symbol:string):Promise<{status:number;raw:string;asof:string}>}
export class Coordinator {
  constructor(readonly store:Store,readonly collector:Collector,readonly clock:(()=>number)|null=null) {}
  start(date:string,now:number) {
    this.store.guard();if(!calendar[date]||latestSession(now)!==date)throw Error('INVALID_TARGET_SESSION');
    return this.store.tx(()=> {
      if(this.store.q('SELECT 1 FROM runs WHERE date=?',date).length)return 'DUPLICATE';
      if(this.store.q("SELECT 1 FROM runs WHERE status IN ('RUNNING','UNCERTAIN_EXECUTION','STATE_ERROR') LIMIT 1").length)throw Error('OVERLAPPING_RUN_BLOCKED');
      for(const symbol of SYMBOLS)this.store.state(symbol); // Missing or corrupt committed state stops before any request.
      this.store.q("INSERT INTO runs VALUES (?,'RUNNING',?)",date,now);
      SYMBOLS.forEach((symbol,i)=>this.store.q("INSERT INTO claims(key,date,symbol,ordinal,status) VALUES (?,?,?,?,'READY')",date+'/'+symbol,date,symbol,i));return 'STARTED';
    });
  }
  async tick(date:string,now:number,fault?:string) {
    this.store.guard();const run=this.store.q('SELECT * FROM runs WHERE date=?',date)[0];if(!run||run.status!=='RUNNING')return run?.status??'NO_RUN';
    // Durable request declarations survive crashes. Never retry an ambiguous call.
    const abandoned=this.store.q("SELECT * FROM claims WHERE date=? AND status='REQUEST_CLAIMED' LIMIT 1",date)[0];
    if(abandoned) {this.store.tx(()=> {this.store.q("UPDATE claims SET status='UNCERTAIN_EXECUTION',error='MANUAL_NETWORK_RECONCILIATION_REQUIRED' WHERE key=?",abandoned.key);this.store.q("UPDATE runs SET status='UNCERTAIN_EXECUTION',updated=? WHERE date=?",now,date);});return 'UNCERTAIN_EXECUTION';}
    const task=this.store.q("SELECT * FROM claims WHERE date=? AND status IN ('READY','EVIDENCE_SAVED') ORDER BY ordinal LIMIT 1",date)[0];
    if(!task){this.store.q("UPDATE runs SET status='COMPLETE',updated=? WHERE date=?",now,date);return 'COMPLETE';}
    const symbol=task.symbol;let previous;
    try {previous=this.store.state(symbol);}catch(e) {this.fail(task,'STATE_ERROR',e,now);return 'STATE_ERROR';}
    if(previous&&missing(previous.doc.trading_date,date).length) {this.fail(task,'CATCHUP_REQUIRED',Error('Missing Point-in-Time captures: '+missing(previous.doc.trading_date,date).join(',')),now);return 'CATCHUP_REQUIRED';}
    if(previous&&date<previous.doc.trading_date){this.fail(task,'DATA_ERROR',Error('STALE_DATA'),now);return 'DATA_ERROR';}
    let response:any;
    if(task.status==='READY') {
      const last=this.store.q('SELECT * FROM claims WHERE started IS NOT NULL ORDER BY started DESC LIMIT 1')[0];
      const boundary=last&&Math.floor(task.ordinal/3)!==Math.floor(last.ordinal/3),wait=5000+(boundary?30000:0);
      // Pace from the completed response, conservatively later than the actual
      // network start. A slow durable sync must not shorten the true start gap.
      if(last&&now<(last.finished??last.started)+wait)return 'WAIT';
      this.store.tx(()=> {if(this.store.q('SELECT status FROM claims WHERE key=?',task.key)[0].status!=='READY')throw Error('CLAIM_CONFLICT');this.store.q("UPDATE claims SET status='REQUEST_CLAIMED',started=? WHERE key=?",now,task.key);});
      // DO adapter awaits storage.sync() here, before collector is invoked.
      if(fault==='before_request')throw Error('INJECTED_CRASH_BEFORE_REQUEST');
      try {response=await this.collector.collect(symbol);}catch(e) {this.fail(task,'UNCERTAIN_EXECUTION',e,now);return 'UNCERTAIN_EXECUTION';}
      if(fault==='after_request'||fault==='raw_write')throw Error('INJECTED_UNKNOWN_RESULT');
      this.store.tx(()=> {const hash=this.store.putEvidence(task.key,canonical(response));this.store.q("UPDATE claims SET raw_hash=?,finished=? WHERE key=?",hash,this.clock?this.clock():now,task.key);this.store.q("UPDATE claims SET status='EVIDENCE_SAVED' WHERE key=? AND status='REQUEST_CLAIMED'",task.key);});
      if(this.store.q('SELECT status FROM claims WHERE key=?',task.key)[0]?.status!=='EVIDENCE_SAVED')return 'UNCERTAIN_EXECUTION';
    } else {
      const row=this.store.q('SELECT * FROM evidence WHERE key=?',task.key)[0];if(!row||digest(row.raw)!==row.hash||row.hash!==task.raw_hash){this.fail(task,'STATE_ERROR',Error('RAW_HASH_MISMATCH'),now);return 'STATE_ERROR';}response=JSON.parse(row.raw);
    }
    if(response.status!==200) {
      const status=response.status;
      this.fail(task,'DATA_ERROR',Error('HTTP_'+status),now);
      if(status===429||([401,403].includes(status)&&this.store.q("SELECT 1 FROM claims WHERE date=? AND error IN ('HTTP_401','HTTP_403')",date).length>=2))this.store.q("UPDATE runs SET status='DATA_ERROR',updated=? WHERE date=?",now,date);
      return 'DATA_ERROR';
    }
    try {
      const sample=validateYahoo(symbol,JSON.parse(response.raw),response.asof);if(sample.target!==date)throw Error('STALE_DATA');
      if(previous?.doc.rejected_snapshot_fingerprints?.includes(pythonPriceFingerprint(Object.fromEntries(sample.pairs))))throw Error('REJECTED_REVISION_SNAPSHOT');
      const ledger=this.store.ledger(symbol),model=await evaluate(symbol,sample.pairs,sample.closes,sample.identity,previous?.doc??null,1,ledger,INDICES.includes(symbol)?'INDEX':'EQUITY');
      const events=[...model.market_events];if(model.revision_observation.detected)events.push({symbol,trading_date:date,event_type:'REVISION_OBSERVATION',threshold:null,status:model.revision_observation.requires_review?'PENDING_REVIEW':'CONFIRMED',rules_version:RULES,evidence:{revision_observation:model.revision_observation,previous_valid_stock:previous?.doc??null,snapshot_fingerprint:digest(canonical(Object.fromEntries(sample.pairs)))}});
      for(const e of events)register(ledger,await stableId(e,INDICES.includes(symbol)),e,INDICES.includes(symbol));
      const pending=Object.keys(ledger).filter(id=>ledger[id].symbol===symbol&&ledger[id].status==='PENDING_REVIEW').sort();
      const confirmed=unique([...(previous?.doc.confirmed_thresholds??[]),...Object.values(ledger).filter((e:any)=>e.symbol===symbol&&['THRESHOLD_CROSSING','LEGACY_THRESHOLD_REVIEW'].includes(e.event_type)&&e.status==='CONFIRMED'&&e.threshold!==null).map((e:any)=>e.threshold)]);
      const doc={...model,symbol,history_prices:Object.fromEntries(sample.pairs),history_closes:sample.closes,identity_snapshot:sample.identity,data_quality:sample.data_quality,source_as_of_utc:sample.as_of_utc,rules_version:RULES,event_model_version:INDICES.includes(symbol)?'indices-revision-market-v2':'revision-market-v2',confirmed_thresholds:confirmed,triggered_thresholds:confirmed,threshold_state:{...model.threshold_state,confirmed,pending_event_ids:pending},revision_review_event_ids:pending.filter(id=>ledger[id].event_type==='REVISION_OBSERVATION'),rejected_snapshot_fingerprints:previous?.doc.rejected_snapshot_fingerprints??[]};
      this.store.commit(task.key,symbol,previous?.version??null,doc,ledger,fault);return 'COMMITTED';
    }catch(e) {
      if(fault==='state_write'||fault==='event_write')throw e; // Evidence retained; retry processing only.
      this.fail(task,'DATA_ERROR',e,now);return 'DATA_ERROR';
    }
  }
  fail(task:R,status:string,error:any,now:number) {this.store.tx(()=> {this.store.q('UPDATE claims SET status=?,error=? WHERE key=?',status,String(error.message??error),task.key);if(['UNCERTAIN_EXECUTION','STATE_ERROR'].includes(status))this.store.q('UPDATE runs SET status=?,updated=? WHERE date=?',status,now,task.date);});}
}
