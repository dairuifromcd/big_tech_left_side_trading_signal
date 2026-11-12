import {createHash} from 'node:crypto';
import {RecordValue as R,sorted,RULES,SYMBOLS,INDICES,calculate,closeEnough,tier,Pair,semanticJson} from './core.ts';
export interface Sql {exec(query:string,...bindings:any[]):{toArray():any[];rowsRead?:number;rowsWritten?:number}}
export interface Backend {sql:Sql;transactionSync<T>(fn:()=>T):T}
export const canonical=(x:any)=>JSON.stringify(sorted(x),(_k,v)=>{if(typeof v==='number'&&!Number.isFinite(v))throw Error('NON_FINITE');return v;});
export const digest=(s:string)=>createHash('sha256').update(s).digest('hex');
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
  reads=0;writes=0;statements=0;
  constructor(readonly db:Backend) {}
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
  }
  q(sql:string,...args:any[]) {this.statements++;const c=this.db.sql.exec(sql,...args);const rows=c.toArray();this.reads+=c.rowsRead??rows.length;this.writes+=c.rowsWritten??0;return rows;}
  tx<T>(f:()=>T) {return this.db.transactionSync(f);}
  initialized() {return this.q("SELECT value FROM meta WHERE key='receipt'").length>0;}
  initialize() {
    this.setup();
    this.tx(()=> {
      if(this.q('SELECT * FROM meta').length||['states','events','runs','claims','evidence','history','backups'].some(t=>this.q(`SELECT 1 FROM ${t} LIMIT 1`).length))throw Error('INITIALIZATION_REFUSED');
      this.q("INSERT INTO meta VALUES ('receipt','EXPLICIT_OFFLINE_INITIALIZATION')");this.q("INSERT INTO meta VALUES ('schema','1')");
    });
  }
  guard() {if(!this.initialized())throw Error('STATE_ERROR: MISSING_INITIALIZATION_RECEIPT');if(this.q("SELECT value FROM meta WHERE key='schema'")[0]?.value!=='1')throw Error('STATE_ERROR: INCOMPATIBLE_SCHEMA');}
  unpack(row:any) {if(digest(row.version===undefined?row.body:`${row.version}:${row.body}`)!==row.hash)throw Error('STATE_ERROR: HASH_MISMATCH');return JSON.parse(row.body);}
  state(symbol:string) {
    this.guard();const row=this.q('SELECT * FROM states WHERE category=? AND symbol=?',category(symbol),symbol)[0];
    if(!row) {
      if(this.q("SELECT 1 FROM claims WHERE symbol=? AND status='COMMITTED' LIMIT 1",symbol).length)throw Error('STATE_ERROR: MISSING_COMMITTED_STATE');
      return null;
    }
    const doc=this.unpack(row);this.validateState(symbol,doc);return {version:row.version,doc};
  }
  validateState(symbol:string,doc:R) {
    if(doc.symbol!==symbol||doc.rules_version!==RULES)throw Error('STATE_ERROR: SYMBOL_OR_RULES');
    const m=calculate(Object.entries(doc.history_prices).sort() as Pair[],doc.trading_date,symbol==='SPCX');
    for(const k of ['adjclose','highest_adjclose','drawdown','rsi14','sma50','sma200'])if(m[k]===null?doc[k]!==null:typeof doc[k]!=='number'||!Number.isFinite(doc[k])||!closeEnough(m[k],doc[k]))throw Error('STATE_ERROR: INDICATORS');
    if(doc.highest_date!==m.highest_date||doc.watch_tier!==tier(m.drawdown)||!Number.isFinite(doc.deepening_anchor))throw Error('STATE_ERROR: SEMANTICS');
    for(const values of [doc.confirmed_thresholds,doc.threshold_state?.confirmed,doc.triggered_thresholds])if(!Array.isArray(values)||values.some((n:number)=>![10,20,30].includes(n))||canonical(values)!==canonical([...new Set(values)].sort((a:any,b:any)=>a-b)))throw Error('STATE_ERROR: THRESHOLD_SCHEMA');
    if(canonical(doc.confirmed_thresholds)!==canonical(doc.threshold_state.confirmed)||canonical(doc.confirmed_thresholds)!==canonical(doc.triggered_thresholds))throw Error('STATE_ERROR: THRESHOLD_ALIAS');
  }
  ledger(symbol:string) {this.guard();return Object.fromEntries(this.q('SELECT * FROM events WHERE category=?',category(symbol)).map(r=>[r.id,this.unpack(r)]));}
  putEvidence(key:string,raw:string,origin='MOCK_POINT_IN_TIME') {
    if(raw.length>1_000_000)throw Error('DATA_ERROR: EVIDENCE_REQUIRES_CHUNKING');
    const hash=digest(raw),old=this.q('SELECT hash,raw,origin FROM evidence WHERE key=?',key)[0];
    if(old) {if(old.hash!==hash||old.raw!==raw||old.origin!==origin)throw Error('IMMUTABLE_EVIDENCE_CONFLICT');return hash;}
    this.q('INSERT INTO evidence VALUES (?,?,?,?)',key,raw,hash,origin);return hash;
  }
  commit(key:string,symbol:string,priorVersion:number|null,doc:R,ledger:R,fault?:string) {
    this.validateState(symbol,doc);const body=canonical(doc);
    this.tx(()=> {
      this.guard();const old=this.state(symbol);
      for(const level of doc.confirmed_thresholds)if(!Object.values(ledger).some((e:any)=>e.symbol===symbol&&e.threshold===level&&['THRESHOLD_CROSSING','LEGACY_THRESHOLD_REVIEW'].includes(e.event_type)&&e.status==='CONFIRMED'))throw Error('STATE_ERROR: CONFIRMED_WITHOUT_EVENT');
      for(const id of doc.threshold_state.pending_event_ids)if(ledger[id]?.symbol!==symbol||ledger[id]?.status!=='PENDING_REVIEW')throw Error('STATE_ERROR: PENDING_REFERENCE');
      if((old?.version??null)!==priorVersion)throw Error('STATE_ERROR: CAS_CONFLICT');
      if(this.q('SELECT status FROM claims WHERE key=?',key)[0]?.status!=='EVIDENCE_SAVED')throw Error('STATE_ERROR: CLAIM_NOT_READY');
      const version=(priorVersion??0)+1;
      const hash=digest(`${version}:${body}`);
      this.q('INSERT INTO states VALUES (?,?,?,?,?) ON CONFLICT(category,symbol) DO UPDATE SET version=excluded.version,body=excluded.body,hash=excluded.hash',category(symbol),symbol,version,body,hash);
      if(fault==='state_write')throw Error('INJECTED_STATE_WRITE');
      for(const [id,event] of Object.entries(ledger)) {
        const text=canonical(event),hash=digest(text);
        if(this.q('SELECT hash FROM events WHERE category=? AND id=?',category(symbol),id)[0]?.hash!==hash)
          this.q('INSERT INTO events VALUES (?,?,?,?) ON CONFLICT(category,id) DO UPDATE SET body=excluded.body,hash=excluded.hash',category(symbol),id,text,hash);
      }
      if(fault==='event_write')throw Error('INJECTED_EVENT_WRITE');
      const report=canonical(reportAsset(doc));
      this.q('INSERT INTO history VALUES (?,?,?,?,?,?)',category(symbol),symbol,doc.trading_date,version,report,digest(`${version}:${report}`));
      this.q("UPDATE claims SET status='COMMITTED' WHERE key=?",key);
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
