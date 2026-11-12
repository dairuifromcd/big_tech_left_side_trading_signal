import {RecordValue as R, SYMBOLS, STOCKS, INDICES, RULES, calendar, Pair, calculate, closeEnough,
  crossed, tier, checkDate, eventSemantic, semanticJson, positive} from './core.ts';
import {canonical, digest} from './integrity.ts';
import {validateIdentity, validateYahoo} from './yahoo.ts';

const statuses = ['CONFIRMED','PENDING_REVIEW','REJECTED'];
const eventTypes = ['THRESHOLD_CROSSING','LEGACY_THRESHOLD_REVIEW','DEEPER_DRAWDOWN','RECOVERY','REENTRY','REVISION_OBSERVATION'];
const record = (value:any):value is R => !!value && typeof value === 'object' && !Array.isArray(value);
export function stateError(code:string, reference=''):never {throw Error(`STATE_ERROR: ${code}${reference ? ' ['+reference+']' : ''}`);}
function requireThat(condition:any, code:string, reference=''):asserts condition {if (!condition) stateError(code,reference);}
export const assetCategory = (symbol:string) => INDICES.includes(symbol) ? 'indices' : 'stocks';
const model = (symbol:string) => INDICES.includes(symbol) ? 'indices-revision-market-v2' : 'revision-market-v2';
function stringSet(value:any, code:string) {
  requireThat(Array.isArray(value) && value.every(v=>typeof v==='string') && canonical(value)===canonical([...new Set(value)].sort()),code);
  return value as string[];
}
function levels(value:any) {
  requireThat(Array.isArray(value) && value.every(v=>[10,20,30].includes(v)) && canonical(value)===canonical([...new Set(value)].sort((a:any,b:any)=>a-b)),'THRESHOLD_SCHEMA');
  return value as number[];
}
export function validateStateContent(symbol:string, doc:R) {
  requireThat(SYMBOLS.includes(symbol) && record(doc) && doc.symbol===symbol && doc.rules_version===RULES,'SYMBOL_OR_RULES',symbol);
  requireThat(doc.event_model_version===model(symbol),'EVENT_MODEL_VERSION',symbol);
  requireThat(doc.checkpoint_schema_version===undefined || doc.checkpoint_schema_version===1,'STATE_SCHEMA',symbol);
  requireThat(record(doc.history_prices) && record(doc.history_closes) && record(doc.identity_snapshot),'HISTORY_PROVENANCE',symbol);
  const dates=Object.keys(doc.history_prices).sort();
  requireThat(canonical(dates)===canonical(Object.keys(doc.history_closes).sort()) && dates.every(d=>positive(doc.history_closes[d])),'HISTORY_CLOSES',symbol);
  requireThat(dates.at(-1)===doc.trading_date && doc.adjclose===doc.history_prices[doc.trading_date],'STATE_DATE_PRICE',symbol);
  checkDate(doc.trading_date);
  validateIdentity(symbol,doc.identity_snapshot);
  const rows=dates.map(d=>[d,doc.history_prices[d]] as Pair);
  const m=calculate(rows,doc.trading_date,symbol==='SPCX');
  for(const k of ['adjclose','highest_adjclose','drawdown','rsi14','sma50','sma200']) {
    requireThat(m[k]===null ? doc[k]===null : typeof doc[k]==='number' && Number.isFinite(doc[k]) && closeEnough(m[k],doc[k]),'INDICATORS',symbol);
  }
  requireThat(doc.highest_date===m.highest_date && doc.watch_tier===tier(m.drawdown) && Number.isFinite(doc.deepening_anchor),'SEMANTICS',symbol);
  requireThat(doc.window_samples===m.window_samples && canonical(doc.indicator_status)===canonical(m.indicator_status),'INDICATOR_METADATA',symbol);
  requireThat(record(doc.threshold_state),'THRESHOLD_STATE',symbol);
  for(const values of [doc.confirmed_thresholds,doc.triggered_thresholds,doc.threshold_state.confirmed,doc.threshold_state.baseline,doc.baseline_observed_thresholds,doc.threshold_state.observed])levels(values);
  requireThat(canonical(doc.confirmed_thresholds)===canonical(doc.threshold_state.confirmed) && canonical(doc.confirmed_thresholds)===canonical(doc.triggered_thresholds),'THRESHOLD_ALIAS',symbol);
  requireThat(canonical(doc.threshold_state.baseline)===canonical(doc.baseline_observed_thresholds) && canonical(doc.threshold_state.observed)===canonical(crossed(doc.drawdown)),'THRESHOLD_OBSERVED_BASELINE',symbol);
  stringSet(doc.threshold_state.pending_event_ids,'PENDING_REFERENCE_SCHEMA');
  stringSet(doc.revision_review_event_ids,'REVISION_REFERENCE_SCHEMA');
  requireThat(typeof doc.source_as_of_utc==='string','CAPTURE_TIME',symbol);
  // Re-run the existing identity/calendar/history gate on stored normalized provenance.
  validateYahoo(symbol,{chart:{result:[{meta:doc.identity_snapshot,timestamp:dates.map(d=>calendar[d]![0]/1000),
    indicators:{adjclose:[{adjclose:rows.map(r=>r[1])}],quote:[{close:dates.map(d=>doc.history_closes[d])}]}}]}},doc.source_as_of_utc);
  requireThat(['PASS','PASS_PROVISIONAL'].includes(doc.data_quality) && (symbol!=='SPCX' || doc.data_quality==='PASS_PROVISIONAL'),'DATA_QUALITY',symbol);
}

export function validateEvent(category:string, id:string, event:R) {
  requireThat(record(event) && SYMBOLS.includes(event.symbol) && category===assetCategory(event.symbol),'EVENT_CATEGORY_SYMBOL',id);
  requireThat(event.event_id===id && event.rules_version===RULES && event.event_model_version===model(event.symbol),'EVENT_SCHEMA',id);
  requireThat(INDICES.includes(event.symbol) ? event.category==='Market Indices' : event.category===undefined,'EVENT_CATEGORY_FIELD',id);
  requireThat(eventTypes.includes(event.event_type) && statuses.includes(event.status),'EVENT_TYPE_STATUS',id);
  requireThat(digest(semanticJson(eventSemantic(event,INDICES.includes(event.symbol))))===id,'EVENT_SEMANTIC_ID',id);
  if(['THRESHOLD_CROSSING','LEGACY_THRESHOLD_REVIEW'].includes(event.event_type)) {
    requireThat([10,20,30].includes(event.threshold),'EVENT_THRESHOLD',id);
    if(event.event_type==='THRESHOLD_CROSSING')requireThat(['NEW_THRESHOLD','REENTRY'].includes(event.event_subtype),'EVENT_SUBTYPE',id);
  }else requireThat(event.threshold===null,'EVENT_THRESHOLD',id);
  requireThat(Array.isArray(event.evidence_versions) && event.evidence_versions.length>0,'EVIDENCE_VERSIONS',id);
  const hashes=new Set<string>();
  for(const version of event.evidence_versions) {
    requireThat(record(version) && record(version.evidence) && typeof version.evidence_hash==='string','EVIDENCE_SCHEMA',id);
    if(!version.hash_scheme || version.hash_scheme==='python-json-v1')stateError('LEGACY_EVIDENCE_MIGRATION_REQUIRED',id);
    requireThat(version.hash_scheme==='js-canonical-v1','UNSUPPORTED_EVIDENCE_HASH_SCHEME',id);
    requireThat(digest(canonical(version.evidence))===version.evidence_hash,'EVIDENCE_HASH',id);
    requireThat(!hashes.has(version.evidence_hash),'DUPLICATE_EVIDENCE_VERSION',id);hashes.add(version.evidence_hash);
  }
  requireThat(Array.isArray(event.audit_trail) && event.audit_trail.length>0,'AUDIT_TRAIL',id);
  let previous:string|null=null;
  for(let i=0;i<event.audit_trail.length;i++) {
    const audit=event.audit_trail[i];
    requireThat(record(audit) && statuses.includes(audit.to_status) && audit.from_status===previous,'AUDIT_CHAIN',id);
    if(i===0)requireThat(audit.action==='REGISTER','AUDIT_INITIAL_ACTION',id);
    else if(audit.action==='RISK_ESCALATION') {
      requireThat(event.event_type==='REVISION_OBSERVATION' && previous==='CONFIRMED' && audit.to_status==='PENDING_REVIEW' &&
        event.evidence_versions.some((v:R)=>v.evidence_hash===audit.evidence_hash && v.evidence.revision_observation?.requires_review===true),'AUDIT_ESCALATION',id);
    }else if(audit.action==='DEPENDENCY_RISK') {
      requireThat(previous==='CONFIRMED' && audit.to_status==='CONFIRMED' && typeof audit.revision_event_id==='string','AUDIT_DEPENDENCY',id);
    }else stateError('UNSUPPORTED_AUDIT_TRANSITION_REQUIRES_MIGRATION',id);
    previous=audit.to_status;
  }
  requireThat(previous===event.status,'AUDIT_FINAL_STATUS',id);
  const refs=event.dependency_review_event_ids===undefined?[]:stringSet(event.dependency_review_event_ids,'DEPENDENCY_REFERENCE_SCHEMA');
  const auditRefs=[...new Set<string>(event.audit_trail.filter((a:R)=>a.action==='DEPENDENCY_RISK').map((a:R)=>a.revision_event_id))].sort();
  requireThat(canonical(refs)===canonical(auditRefs) && (refs.length>0 ? event.dependency_review_required===true : event.dependency_review_required!==true),'DEPENDENCY_FLAGS',id);
}

export function validateReferences(symbol:string, doc:R, events:R) {
  const related=Object.entries(events).filter(([,event])=>event.symbol===symbol);
  const confirmed=[...new Set(related.filter(([,e])=>['THRESHOLD_CROSSING','LEGACY_THRESHOLD_REVIEW'].includes(e.event_type) && e.status==='CONFIRMED').map(([,e])=>e.threshold))].sort((a,b)=>a-b);
  requireThat(canonical(doc.confirmed_thresholds)===canonical(confirmed),'CONFIRMED_WITHOUT_EVENT_OR_REFERENCE',symbol);
  const pending=related.filter(([,e])=>e.status==='PENDING_REVIEW').map(([id])=>id).sort();
  requireThat(canonical(doc.threshold_state.pending_event_ids)===canonical(pending),'PENDING_REFERENCE',symbol);
  const revisions=related.filter(([,e])=>e.status==='PENDING_REVIEW' && e.event_type==='REVISION_OBSERVATION').map(([id])=>id).sort();
  requireThat(canonical(doc.revision_review_event_ids)===canonical(revisions),'REVISION_REFERENCE',symbol);
  for(const [id,event] of related) {
    requireThat(event.trading_date<=doc.trading_date,'EVENT_AFTER_STATE',id);
    for(const ref of event.dependency_review_event_ids??[]) {
      const dependency=events[ref];
      requireThat(dependency?.symbol===symbol && dependency.event_type==='REVISION_OBSERVATION' && dependency.trading_date<=event.trading_date,'DEPENDENCY_REFERENCE',id);
    }
  }
}

export function preserveDecisions(previous:R, next:R, symbol:string) {
  for(const [id,old] of Object.entries(previous))if(old.symbol===symbol) {
    const current=next[id];requireThat(current && current.symbol===symbol,'EVENT_REMOVAL',id);
    requireThat(canonical(current.evidence_versions.slice(0,old.evidence_versions.length))===canonical(old.evidence_versions) &&
      canonical(current.audit_trail.slice(0,old.audit_trail.length))===canonical(old.audit_trail),'EVENT_AUDIT_REWRITE',id);
    if(old.status==='REJECTED' || old.status==='PENDING_REVIEW')requireThat(current.status===old.status,'REOPEN_OR_PROMOTION_REQUIRED',id);
    if(old.status==='CONFIRMED' && current.status!=='CONFIRMED')requireThat(old.event_type==='REVISION_OBSERVATION' && current.status==='PENDING_REVIEW' && current.audit_trail.at(-1)?.action==='RISK_ESCALATION','CONFIRMATION_REVOKED',id);
    requireThat((old.dependency_review_event_ids??[]).every((ref:string)=>(current.dependency_review_event_ids??[]).includes(ref)),'DEPENDENCY_REMOVAL',id);
  }
}
