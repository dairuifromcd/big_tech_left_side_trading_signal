import {RecordValue as R,sorted,RULES,SYMBOLS,INDICES,calculate,closeEnough,tier,Pair,semanticJson} from './core.ts';
import {canonical, digest} from './integrity.ts';
import {InitializationReceipt, localTestReceipt, verifyReceipt} from './initialization.ts';
import {stateError, validateStateContent, validateEvent, validateReferences, preserveDecisions} from './checkpoint.ts';
import {validateYahoo} from './yahoo.ts';
export {canonical, digest} from './integrity.ts';
export interface Sql {exec(query:string,...bindings:any[]):{toArray():any[];rowsRead?:number;rowsWritten?:number}}
export interface Backend {sql:Sql;transactionSync<T>(fn:()=>T):T}
// Python price maps contain normalized float64 values, including integral floats.
// This is deliberately separate from general evidence hashing: arbitrary mixed
// Python int/float JSON cannot be losslessly inferred after JSON.parse().
export function pythonPriceFingerprint(prices:Record<string,number>) {
  const number=(n:number)=> {
    if(!Number.isFinite(n))throw Error('NON_FINITE');
    if(Object.is(n,-0))return '-0.0';
    if(n!==0&&(Math.abs(n)<1e-4||Math.abs(n)>=1e16))return n.toExponential().replace(/e([+-])(\d)$/, 'e$10$2');
    const s=String(n);return s.includes('.')?s:s+'.0';
  };
  return digest('{'+Object.keys(prices).sort().map(k=>semanticJson(k)+': '+number(prices[k])).join(', ')+'}');
}
export const category=(s:string)=>INDICES.includes(s)?'indices':'stocks';
export function register(ledger:R,id:string,event:R,index=false) {
  const status=event.status??'PENDING_REVIEW';if(!['CONFIRMED','PENDING_REVIEW','REJECTED'].includes(status))throw Error('EVENT_STATUS_ERROR');
  const evidence=structuredClone(event.evidence??{}),version={evidence_hash:digest(canonical(evidence)),hash_scheme:'js-canonical-v1',evidence};
  const old=ledger[id];
  if(old) {
    if(old.evidence_versions.some((v:R)=>v.evidence_hash===version.evidence_hash))return;
    if(old.status==='REJECTED'&&(index||event.event_type==='REVISION_OBSERVATION'))throw Error('REOPEN_REQUIRED');
    if(old.status==='REJECTED')throw Error('REOPEN_REQUIRED');
    const escalation=old.status==='CONFIRMED'&&status==='PENDING_REVIEW'&&event.event_type==='REVISION_OBSERVATION';
    if(escalation&&!index&&evidence.revision_observation?.requires_review!==true)throw Error('RISK_EVIDENCE_REQUIRED');
    old.evidence_versions.push(version);
    if(escalation){old.status='PENDING_REVIEW';old.audit_trail.push({action:'RISK_ESCALATION',from_status:'CONFIRMED',to_status:'PENDING_REVIEW',evidence_hash:version.evidence_hash});}
  }else {
    const {evidence:_e,...rest}=event;
    ledger[id]={...structuredClone(rest),rules_version:RULES,event_model_version:index?'indices-revision-market-v2':'revision-market-v2',...(index?{category:'Market Indices'}:{}),event_id:id,status,evidence_versions:[version],audit_trail:[{action:'REGISTER',from_status:null,to_status:status}]};
  }
  if(event.event_type==='REVISION_OBSERVATION'&&ledger[id].status==='PENDING_REVIEW')for(const other of Object.values(ledger) as R[]) {
    if(other.symbol===event.symbol&&other.trading_date>=event.trading_date&&other.status==='CONFIRMED'&&other.event_type!=='REVISION_OBSERVATION') {
      other.dependency_review_required=true;const refs=other.dependency_review_event_ids??[];
      if(!refs.includes(id)){other.dependency_review_event_ids=[...refs,id].sort();other.audit_trail.push({action:'DEPENDENCY_RISK',from_status:'CONFIRMED',to_status:'CONFIRMED',revision_event_id:id});}
    }
  }
}
export class Store {
  reads=0;writes=0;statements=0;fullValidations=0;
  constructor(readonly db:Backend, readonly objectId?:string, readonly evidenceOrigin:'MOCK_POINT_IN_TIME'|'MOCK_ONLY_SYNTHETIC_V1'='MOCK_POINT_IN_TIME') {}
  setup() {
    // Creating empty schema does not initialize monitoring state or a baseline.
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS states (category TEXT NOT NULL, symbol TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(category,symbol))');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS events (category TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(category,id))');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS runs (date TEXT PRIMARY KEY, status TEXT NOT NULL, updated INTEGER NOT NULL)');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS claims (key TEXT PRIMARY KEY, date TEXT NOT NULL, symbol TEXT NOT NULL, ordinal INTEGER NOT NULL, status TEXT NOT NULL, started INTEGER, finished INTEGER, error TEXT, raw_hash TEXT)');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS evidence (key TEXT PRIMARY KEY, raw TEXT NOT NULL, hash TEXT NOT NULL, origin TEXT NOT NULL)');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS history (category TEXT NOT NULL, symbol TEXT NOT NULL, date TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(category,symbol,date,version))');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS backups (id TEXT PRIMARY KEY, body TEXT NOT NULL, hash TEXT NOT NULL)');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS initialization_audit (id TEXT PRIMARY KEY, body TEXT NOT NULL, hash TEXT NOT NULL)');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS checkpoint_control (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL, validated_generation INTEGER NOT NULL, checkpoint_hash TEXT NOT NULL)');
    this.db.sql.exec('CREATE TABLE IF NOT EXISTS run_checkpoints (date TEXT PRIMARY KEY, generation INTEGER NOT NULL, checkpoint_hash TEXT NOT NULL)');
    for(const table of this.protectedTables)for(const action of ['INSERT','UPDATE','DELETE'])
      this.db.sql.exec(this.triggerSql(table,action));
  }
  private readonly protectedTables=['states','events','evidence','history','meta','initialization_audit'];
  private triggerSql(table:string,action:string) {return `CREATE TRIGGER checkpoint_${table}_${action.toLowerCase()} AFTER ${action} ON ${table} BEGIN UPDATE checkpoint_control SET generation=generation+1 WHERE id=1; END`;}
  q(sql:string,...args:any[]) {this.statements++;const c=this.db.sql.exec(sql,...args);const rows=c.toArray();this.reads+=c.rowsRead??rows.length;this.writes+=c.rowsWritten??0;return rows;}
  tx<T>(f:()=>T) {return this.db.transactionSync(f);}
  initialized() {return this.q("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").length>0 && this.q("SELECT value FROM meta WHERE key='receipt'").length>0;}
  initialize(receipt:InitializationReceipt=localTestReceipt(), fault?:'after_schema'|'after_receipt', bootstrap?:()=>void) {
    this.tx(()=> {
      // Even empty old application tables are remnants, never proof of a new DO.
      const objects=this.q("SELECT name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'");
      if(objects.length)throw Error('INITIALIZATION_REFUSED: NONEMPTY_OR_EXISTING_SCHEMA');
      const body=canonical(receipt),hash=digest(body);verifyReceipt(body,hash,body,hash);
      if(this.objectId && receipt.target_object_id!==this.objectId)throw Error('INITIALIZATION_TARGET_MISMATCH');
      this.setup();
      if(fault==='after_schema')throw Error('INJECTED_INITIALIZATION_FAILURE');
      this.q("INSERT INTO checkpoint_control VALUES (1,0,-1,'')");
      this.q("INSERT INTO meta VALUES ('receipt',?)",body);this.q("INSERT INTO meta VALUES ('receipt_hash',?)",hash);
      if(fault==='after_receipt')throw Error('INJECTED_INITIALIZATION_FAILURE');
      this.q("INSERT INTO meta VALUES ('schema','1')");
      this.q('INSERT INTO initialization_audit VALUES (?,?,?)',receipt.receipt_id,body,hash);
      // Trusted adapter only: bootstrap the isolated experiment budget in the
      // same transaction as H01. Never expose this callback through an RPC.
      bootstrap?.();
    });
  }
  guard() {
    try {
      if(!this.initialized())stateError('MISSING_INITIALIZATION_RECEIPT');
      if(this.q("SELECT value FROM meta WHERE key='schema'")[0]?.value!=='1')stateError('INCOMPATIBLE_SCHEMA');
      const body=this.q("SELECT value FROM meta WHERE key='receipt'")[0].value;
      if(body==='EXPLICIT_OFFLINE_INITIALIZATION')stateError('LEGACY_INITIALIZATION_MIGRATION_REQUIRED');
      const audit=this.q('SELECT * FROM initialization_audit');
      if(audit.length!==1)stateError('INITIALIZATION_AUDIT');
      const receipt=verifyReceipt(body,this.q("SELECT value FROM meta WHERE key='receipt_hash'")[0]?.value,audit[0].body,audit[0].hash);
      if(audit[0].id!==receipt.receipt_id || (this.objectId && receipt.target_object_id!==this.objectId))stateError('INITIALIZATION_TARGET_BINDING');
    }catch(error) {if(String(error).includes('STATE_ERROR:'))throw error;stateError('INITIALIZATION_INVALID');}
  }
  unpack(row:any) {
    if(row.version!==undefined && (!Number.isSafeInteger(row.version)||row.version<1))stateError('STATE_VERSION');
    if(digest(row.version===undefined?row.body:`${row.version}:${row.body}`)!==row.hash)stateError('HASH_MISMATCH');
    const value=JSON.parse(row.body);if(canonical(value)!==row.body)stateError('NON_CANONICAL_OR_DUPLICATE_JSON');return value;
  }
  state(symbol:string) {
    this.guard();const row=this.q('SELECT * FROM states WHERE category=? AND symbol=?',category(symbol),symbol)[0];
    if(!row) {
      if(this.q("SELECT 1 FROM claims WHERE symbol=? AND status='COMMITTED' LIMIT 1",symbol).length)throw Error('STATE_ERROR: MISSING_COMMITTED_STATE');
      return null;
    }
    const doc=this.unpack(row);this.validateState(symbol,doc);return {version:row.version,doc};
  }
  validateState(symbol:string,doc:R) {
    try {validateStateContent(symbol,doc);}catch(error) {if(String(error).includes('STATE_ERROR:'))throw error;stateError('STATE_PROVENANCE',symbol);}
  }
  private control() {
    const rows=this.q('SELECT * FROM checkpoint_control');const row=rows[0];
    if(rows.length!==1 || row.id!==1 || !Number.isSafeInteger(row.generation) || row.generation<0 || !Number.isSafeInteger(row.validated_generation) || row.validated_generation < -1 || row.validated_generation>row.generation ||
      (row.validated_generation===-1 ? row.checkpoint_hash!=='' : !/^[0-9a-f]{64}$/.test(row.checkpoint_hash)))stateError('CHECKPOINT_CONTROL');
    return row;
  }
  private validateTriggers() {
    const triggers=new Map(this.q("SELECT name,sql FROM sqlite_master WHERE type='trigger'").map(r=>[r.name,r.sql]));
    if(triggers.size!==this.protectedTables.length*3)stateError('CHECKPOINT_TRIGGER_SET');
    for(const table of this.protectedTables)for(const action of ['INSERT','UPDATE','DELETE'])
      if(triggers.get(`checkpoint_${table}_${action.toLowerCase()}`)!==this.triggerSql(table,action))stateError('CHECKPOINT_TRIGGER_MISSING_OR_CHANGED');
  }
  validateFullCheckpoint() {
    this.fullValidations++;
    try {
      this.guard();this.validateTriggers();const control=this.control();
      const states=this.q('SELECT * FROM states ORDER BY category,symbol'),rows=this.q('SELECT * FROM events ORDER BY category,id');
      const documents:R=Object.create(null),events:R=Object.create(null);
      for(const row of states) {
        if(!SYMBOLS.includes(row.symbol)||row.category!==category(row.symbol)||documents[row.symbol])stateError('STATE_CATEGORY_OR_DUPLICATE',row.symbol);
        const doc=this.unpack(row);this.validateState(row.symbol,doc);documents[row.symbol]=doc;
      }
      for(const row of rows) {
        if(events[row.id])stateError('DUPLICATE_OR_CONFLICTING_EVENT',row.id);
        const event=this.unpack(row);validateEvent(row.category,row.id,event);events[row.id]=event;
      }
      for(const event of Object.values(events) as R[])if(!documents[event.symbol])stateError('ORPHAN_EVENT',event.event_id);
      for(const [symbol,doc] of Object.entries(documents))validateReferences(symbol,doc,events);
      const claims=this.q('SELECT * FROM claims ORDER BY key'),runs=new Map(this.q('SELECT * FROM runs').map(r=>[r.date,r]));
      const evidence=this.q('SELECT * FROM evidence ORDER BY key'),evidenceByKey=new Map(evidence.map(r=>[r.key,r]));
      for(const row of evidence)if(digest(row.raw)!==row.hash||row.origin!==this.evidenceOrigin||!claims.some(c=>c.key===row.key))stateError('RAW_EVIDENCE_INTEGRITY',row.key);
      for(const claim of claims) {
        if(!SYMBOLS.includes(claim.symbol)||claim.key!==claim.date+'/'+claim.symbol||claim.ordinal!==SYMBOLS.indexOf(claim.symbol)||!runs.has(claim.date))stateError('CLAIM_REFERENCE',claim.key);
        if(claim.raw_hash && evidenceByKey.get(claim.key)?.hash!==claim.raw_hash)stateError('CLAIM_RAW_REFERENCE',claim.key);
        if(claim.status==='COMMITTED' && (!documents[claim.symbol]||documents[claim.symbol].trading_date<claim.date||!claim.raw_hash))stateError('MISSING_COMMITTED_STATE',claim.symbol);
      }
      const history=this.q('SELECT * FROM history ORDER BY category,symbol,date,version');
      for(const row of history) {
        const doc=this.unpack(row);
        if(!SYMBOLS.includes(row.symbol)||row.category!==category(row.symbol)||doc.symbol!==row.symbol||doc.category!==row.category||doc.trading_date!==row.date)stateError('HISTORY_REFERENCE',row.symbol);
      }
      for(const row of states) {
        const doc=documents[row.symbol],claim=claims.find(c=>c.symbol===row.symbol&&c.date===doc.trading_date&&c.status==='COMMITTED');
        if(!claim)stateError('STATE_WITHOUT_COMMITTED_CLAIM',row.symbol);
        const raw=evidenceByKey.get(claim.key);if(!raw)stateError('MISSING_COMMITTED_RAW',row.symbol);
        const response=JSON.parse(raw.raw),sample=validateYahoo(row.symbol,JSON.parse(response.raw),response.asof);
        if(response.status!==200||response.asof!==doc.source_as_of_utc||canonical(Object.fromEntries(sample.pairs))!==canonical(doc.history_prices)||canonical(sample.closes)!==canonical(doc.history_closes)||canonical(sample.identity)!==canonical(doc.identity_snapshot))stateError('STATE_RAW_PROVENANCE',row.symbol);
        const report=history.find(h=>h.symbol===row.symbol&&h.version===row.version&&h.date===doc.trading_date);
        if(!report||report.body!==canonical(reportAsset(doc)))stateError('STATE_HISTORY_REFERENCE',row.symbol);
      }
      const hash=digest(canonical({generation:control.generation,states:states.map(r=>[r.category,r.symbol,r.version,r.hash]),events:rows.map(r=>[r.category,r.id,r.hash]),evidence:evidence.map(r=>[r.key,r.hash]),history:history.map(r=>[r.category,r.symbol,r.date,r.version,r.hash])}));
      return {generation:control.generation,hash,state_count:states.length,event_count:rows.length};
    }catch(error) {if(String(error).includes('STATE_ERROR:'))throw error;stateError('CHECKPOINT_INVALID');}
  }
  certifyCheckpoint(date:string, proof:ReturnType<Store['validateFullCheckpoint']>) {
    if(this.control().generation!==proof.generation)stateError('CHECKPOINT_CHANGED_DURING_PREFLIGHT');
    this.q('UPDATE checkpoint_control SET validated_generation=?,checkpoint_hash=? WHERE id=1',proof.generation,proof.hash);
    this.q('INSERT INTO run_checkpoints VALUES (?,?,?) ON CONFLICT(date) DO UPDATE SET generation=excluded.generation,checkpoint_hash=excluded.checkpoint_hash',date,proof.generation,proof.hash);
  }
  assertRequestCheckpoint(date:string) {
    this.guard();this.validateTriggers();const row=this.control(),run=this.q('SELECT * FROM run_checkpoints WHERE date=?',date)[0];
    if(row.generation!==row.validated_generation||!run||run.generation!==row.generation||run.checkpoint_hash!==row.checkpoint_hash)stateError('CHECKPOINT_CHANGED_REQUIRES_PREFLIGHT');
  }
  advanceCheckpoint(date:string, verifiedWrite:any) {
    const control=this.control();
    const hash=digest(canonical({previous:control.checkpoint_hash,generation:control.generation,verifiedWrite}));
    this.q('UPDATE checkpoint_control SET validated_generation=generation,checkpoint_hash=? WHERE id=1',hash);
    this.q('UPDATE run_checkpoints SET generation=?,checkpoint_hash=? WHERE date=?',control.generation,hash,date);
  }
  ledger(symbol:string) {this.guard();return Object.fromEntries(this.q('SELECT * FROM events WHERE category=?',category(symbol)).map(r=>[r.id,this.unpack(r)]));}
  putEvidence(key:string,raw:string,origin:string=this.evidenceOrigin) {
    if(raw.length>1_000_000)throw Error('DATA_ERROR: EVIDENCE_REQUIRES_CHUNKING');
    const hash=digest(raw),old=this.q('SELECT hash,raw,origin FROM evidence WHERE key=?',key)[0];
    if(old) {if(old.hash!==hash||old.raw!==raw||old.origin!==origin)throw Error('IMMUTABLE_EVIDENCE_CONFLICT');return hash;}
    this.q('INSERT INTO evidence VALUES (?,?,?,?)',key,raw,hash,origin);return hash;
  }
  commit(key:string,symbol:string,priorVersion:number|null,doc:R,ledger:R,fault?:string) {
    this.validateState(symbol,doc);const body=canonical(doc);
    this.tx(()=> {
      const date=this.q('SELECT date FROM claims WHERE key=?',key)[0]?.date;
      this.assertRequestCheckpoint(date);const old=this.state(symbol),previousLedger=this.ledger(symbol);
      for(const [id,event] of Object.entries(ledger))if(event.symbol===symbol)validateEvent(category(symbol),id,event);
      validateReferences(symbol,doc,ledger);preserveDecisions(previousLedger,ledger,symbol);
      if((old?.version??null)!==priorVersion)throw Error('STATE_ERROR: CAS_CONFLICT');
      if(this.q('SELECT status FROM claims WHERE key=?',key)[0]?.status!=='EVIDENCE_SAVED')throw Error('STATE_ERROR: CLAIM_NOT_READY');
      const version=(priorVersion??0)+1;
      const hash=digest(`${version}:${body}`);
      this.q('INSERT INTO states VALUES (?,?,?,?,?) ON CONFLICT(category,symbol) DO UPDATE SET version=excluded.version,body=excluded.body,hash=excluded.hash',category(symbol),symbol,version,body,hash);
      if(fault==='state_write')throw Error('INJECTED_STATE_WRITE');
      for(const [id,event] of Object.entries(ledger)) {
        const text=canonical(event),hash=digest(text);
        if(event.symbol!==symbol) {
          if(this.q('SELECT hash FROM events WHERE category=? AND id=?',category(symbol),id)[0]?.hash!==hash)stateError('UNRELATED_EVENT_MUTATION',id);
          continue;
        }
        if(this.q('SELECT hash FROM events WHERE category=? AND id=?',category(symbol),id)[0]?.hash!==hash)
          this.q('INSERT INTO events VALUES (?,?,?,?) ON CONFLICT(category,id) DO UPDATE SET body=excluded.body,hash=excluded.hash',category(symbol),id,text,hash);
      }
      if(fault==='event_write')throw Error('INJECTED_EVENT_WRITE');
      const report=canonical(reportAsset(doc));
      this.q('INSERT INTO history VALUES (?,?,?,?,?,?)',category(symbol),symbol,doc.trading_date,version,report,digest(`${version}:${report}`));
      this.q("UPDATE claims SET status='COMMITTED' WHERE key=?",key);
      this.advanceCheckpoint(date,{symbol,state_version:version,state_hash:hash});
    });
  }
  backup(id:string) {
    this.guard();const tables=Object.fromEntries(['meta','states','events','runs','claims','evidence','history'].map(t=>[t,this.q(`SELECT * FROM ${t}`)]));
    const body=canonical({schema:1,tables});const hash=digest(body);this.q('INSERT INTO backups VALUES (?,?,?)',id,body,hash);return {id,hash};
  }
  restore(id:string,approved=false) {
    if(!approved)throw Error('EXPLICIT_RECOVERY_REQUIRED');
    const row=this.q('SELECT * FROM backups WHERE id=?',id)[0];if(!row)throw Error('BACKUP_MISSING');
    const b=this.unpack(row);if(b.schema!==1)throw Error('BACKUP_SCHEMA_ERROR');
    // Never roll back request declarations or event decisions. This local recovery
    // only repairs states from an identical checkpoint; conflict requires reconciliation.
    for(const t of ['meta','events','runs','claims','evidence','history'])if(canonical(this.q(`SELECT * FROM ${t}`))!==canonical(b.tables[t]))throw Error('BACKUP_RECONCILIATION_REQUIRED');
    for(const s of b.tables.states){const d=this.unpack(s);this.validateState(s.symbol,d);}
    this.tx(()=> {this.q('DELETE FROM states');for(const r of b.tables.states)this.q('INSERT INTO states VALUES (?,?,?,?,?)',r.category,r.symbol,r.version,r.body,r.hash);
      this.q('INSERT INTO meta VALUES (?,?)',`recovery:${id}`,row.hash);});
  }
}
export function reportAsset(d:R) {
  const metrics=Object.fromEntries(['adjclose','highest_adjclose','highest_date','drawdown','rsi14','sma50','sma200','window_samples'].map(k=>[k,d[k]]));
  return {symbol:d.symbol,category:category(d.symbol),trading_date:d.trading_date,metrics,watch_tier:d.watch_tier,data_quality:d.data_quality,confirmed_thresholds:d.confirmed_thresholds,pending_event_ids:d.threshold_state.pending_event_ids,daily_drawdown_change_pp:d.daily_drawdown_change_pp,daily_new_deepening:d.daily_new_deepening,cumulative_anchor_deepening_pp:d.cumulative_anchor_deepening_pp,last_candidate_type:d.raw_market_candidate_type,last_candidate_status:d.event_status,source_captured_at:d.source_as_of_utc,origin:'MOCK_OFFLINE',rules_version:RULES};
}
