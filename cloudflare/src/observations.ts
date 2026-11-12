// Direct semantic port of src/observations.py; Python remains the reference.
import {RecordValue as R,Pair,calculate,crossed,tier,transition,unique,equal,positive,revisions,missing,sessions,closeEnough,stableId,RULES,INDICES,checkDate} from './core.ts';
import {sameIdentity} from './yahoo.ts';
const clone=<T>(x:T):T=>structuredClone(x);
const fields=['trading_date','adjclose','window_samples','highest_adjclose','highest_date','drawdown','rsi14','sma50','sma200'];
const view=(m:R)=>Object.fromEntries(fields.map(k=>[k,m[k]]));
function impact(old:R,now:R) {
  const changed=Object.fromEntries(['adjclose','highest_adjclose','highest_date','drawdown','rsi14','sma50','sma200'].map(k=>[k,old[k]!==now[k]]));
  changed.watch_tier=tier(old.drawdown)!==tier(now.drawdown);
  return {changed,deltas:Object.fromEntries(['adjclose','highest_adjclose','drawdown','rsi14','sma50','sma200'].map(k=>[k,old[k]!=null&&now[k]!=null?now[k]-old[k]:null]))};
}
function depth(previous:R|null,current:R,type:string,status:string,latest:R|null=null) {
  const daily=latest??previous;
  return {daily_drawdown_change_pp:daily?(current.drawdown-daily.drawdown)*100:null,daily_new_deepening:!!daily&&current.drawdown<daily.drawdown,stored_previous_drawdown_change_pp:previous?(current.drawdown-previous.drawdown)*100:null,cumulative_anchor_deepening_pp:previous?((previous.deepening_anchor??previous.drawdown)-current.drawdown)*100:null,daily_drawdown_change_basis:latest?'LATEST_ADJCLOSE_SAME_BASIS_PREVIOUS_SESSION':'STORED_PREVIOUS_SESSION_DISPLAY_ONLY',raw_market_candidate_type:type,event_status:status,candidate_confirmed:status==='CONFIRMED'};
}
export function basisComparison(previous:R,pairs:Pair[],touched:number[],significant=1,short=false) {
  const target=pairs.at(-1)![0],old=previous.history_prices;
  const oldCurrent=calculate(pairs.map(([d,p])=>[d,old[d]??p]),target,short);
  const newPrev=calculate(Object.entries({...old,...Object.fromEntries(pairs.filter(([d])=>d<=previous.trading_date))}).sort() as Pair[],previous.trading_date,short);
  const current=calculate(pairs,target,short),oldView={...previous,triggered_thresholds:touched};
  const newView={...oldView,...newPrev,watch_tier:tier(newPrev.drawdown),deepening_anchor:(previous.deepening_anchor??previous.drawdown)+newPrev.drawdown-previous.drawdown};
  return {old_previous:view(previous),old_current:view(oldCurrent),latest_previous:view(newPrev),latest_current:view(current),old_transition:transition(oldView,oldCurrent,significant),latest_transition:transition(newView,current,significant),previous_metric_impacts:impact(previous,newPrev),current_metric_impacts:impact(oldCurrent,current),anchor_rebase_is_conditional:true};
}
const priceRisks=new Set(['RELATIVE_REVISION_NOT_PRECISION_CANDIDATE','ROLLING_EXTREMUM_REVISED','PREVIOUS_EXTREMUM_REVISED','PREVIOUS_TIER_REVISED','COUNTERFACTUAL_EVENT_OR_TIER_DISAGREEMENT','SAME_BASIS_CROSSING_DISAGREEMENT','THRESHOLD_MARGIN_NOT_GREATER_THAN_REVISION_BOUND','DEEPENING_MARGIN_NOT_GREATER_THAN_REVISION_BOUND','UNRESOLVED_PRIOR_REVISION_REVIEW']);
export function dependencies(previous:R,pairs:Pair[],context:R|null,type:string) {
  const symbol=previous.symbol??previous.identity_snapshot?.symbol;
  const inferred=Object.entries(context??{}).filter(([,e])=>e.symbol===symbol&&e.event_type==='REVISION_OBSERVATION'&&e.status==='PENDING_REVIEW').map(([k])=>k);
  let refs:string[]=previous.revision_review_event_ids??(inferred.length?inferred:previous.revision_observation?.requires_review?['LEGACY_UNKNOWN']:[]);
  refs=[...new Set([...refs,...inferred])].sort();
  const support=new Set([...Object.keys(previous.history_prices).sort().slice(-252),...pairs.slice(-252).map(p=>p[0])]);
  return refs.map(key=> {
    const event=context?.[key],versions=event?.evidence_versions??[],dates=new Set<string>();let valid=!!versions.length;
    for(const version of versions) {
      const evidence=version.evidence??{},revision=evidence.revision_observation??{},changes=revision.raw_differences??evidence.changes;
      const legacy=event?.category==='Market Indices'&&Object.hasOwn(evidence,'changes')&&!Object.keys(revision).length;
      if(!legacy&&(!Array.isArray(revision.risk_reasons)||revision.risk_reasons.some((r:string)=>!priceRisks.has(r))))valid=false;
      if(!Array.isArray(changes)||!changes.length){valid=false;continue;}
      for(const change of changes) {try {checkDate(change.date);if(!positive(change.previous)||!positive(change.current))throw Error();dates.add(change.date);}catch{valid=false;}}
    }
    if(event&&(event.status!=='PENDING_REVIEW'||event.event_type!=='REVISION_OBSERVATION'))valid=false;
    const unrelated=valid&&dates.size>0&&![...dates].some(d=>support.has(d))&&type!=='DEEPER_DRAWDOWN';
    return {event_id:key,classification:unrelated?'PROVEN_OUTSIDE_EVENT_WINDOWS':'RELATED_OR_UNPROVEN',revision_dates:[...dates].sort(),review_status_unchanged:true};
  });
}
export async function evaluate(symbol:string,pairs:Pair[],closes:R,identity:R,previousState:R|null,significant=1,context:R|null=null,policy='EQUITY'):Promise<R> {
  const previous=clone(previousState),target=pairs.at(-1)![0],prices=Object.fromEntries(pairs),metrics=calculate(pairs,target,symbol==='SPCX'),now=crossed(metrics.drawdown);
  const thresholds=previous?.threshold_state??{};
  let confirmed=unique(thresholds.confirmed??previous?.confirmed_thresholds??[]),baseline=unique(thresholds.baseline??previous?.baseline_observed_thresholds??[]);
  if(previous&&!Object.keys(thresholds).length&&!baseline.length)baseline=crossed(previous.drawdown);
  const ts={observed:now,confirmed,baseline,pending_event_ids:[...(thresholds.pending_event_ids??[])]};
  let reasons:string[]=[];const raw=revisions(previous,prices);
  const maxAbs=Math.max(0,...raw.map(r=>Math.abs(r.current-r.previous))),maxRel=Math.max(0,...raw.map(r=>Math.abs(r.current/r.previous-1)));
  const revision:R={detected:!!raw.length,classification:raw.length?'REVISION_REVIEW_REQUIRED':'NO_REVISION',count:raw.length,raw_differences:raw,dates:raw.map(r=>r.date),max_absolute_difference:maxAbs,max_relative_difference:maxRel,requires_review:false,confidence:'Observed overlapping-date differences; Yahoo upstream cause unconfirmed'};
  const market:R={previous_trading_date:previous?.trading_date??null,current_trading_date:target,previous_adjclose:previous?.adjclose??null,current_adjclose:metrics.adjclose,previous_drawdown:previous?.drawdown??null,current_drawdown:metrics.drawdown,previous_watch_tier:previous?.watch_tier??null,current_watch_tier:tier(metrics.drawdown),candidate_thresholds:[],crossed_thresholds:[],confirmed_thresholds_this_run:[],pending_thresholds_this_run:[],comparability_proven:false,comparability_reasons:reasons,event_type:previous?'NO_CHANGE':'FIRST_BASELINE',status:'NO_EVENT',can_confirm:false,old_basis_counterfactual:null,previous_recomputed_metrics:null,missing_sessions:previous?missing(previous.trading_date,target):[]};
  if(!previous) {
    ts.baseline=now;
    return {...depth(null,metrics,'FIRST_BASELINE','NO_EVENT'),...metrics,revision_observation:revision,market_observation:market,threshold_state:ts,market_events:[],change_event:'FIRST_BASELINE',watch_tier:tier(metrics.drawdown),previous_watch_tier:null,crossed_thresholds_this_run:[],new_thresholds:[],reentered_thresholds:[],triggered_thresholds:confirmed,confirmed_thresholds:confirmed,baseline_observed_thresholds:now,last_new_trigger_date:null,deepening_anchor:metrics.drawdown,raw_revision_differences:raw};
  }
  const old=previous.history_prices,oldClose=previous.history_closes,overlap=Object.keys(old).filter(d=>Object.hasOwn(prices,d)).sort(),prevDate=previous.trading_date,newSession=target>prevDate,same=target===prevDate;
  if(target<prevDate)throw Error('STALE_DATA');if(!['EQUITY','INDEX'].includes(policy))throw Error('UNKNOWN_IDENTITY_POLICY');
  if(!(policy==='INDEX'?INDICES.includes(symbol)&&equal(identity,previous.identity_snapshot):sameIdentity(symbol,identity,previous.identity_snapshot)))reasons.push('IDENTITY_PROVENANCE_MISSING_OR_CHANGED');
  if(symbol==='SPCX')reasons.push('SPCX_HISTORICAL_ANOMALY_UNVERIFIED');
  if(newSession&&!equal(sessions(prevDate,target),[prevDate,target]))reasons.push('NON_CONSECUTIVE_SESSIONS');
  if(policy!=='INDEX') {
    if(!oldClose||overlap.some(d=>!positive(oldClose[d])||!positive(closes[d])))reasons.push('OVERLAP_CLOSE_EVIDENCE_MISSING');
    else if(overlap.some(d=>oldClose[d]!==closes[d]))reasons.push('OVERLAP_CLOSE_CHANGED');
  }
  if(!Object.hasOwn(prices,prevDate)||prices[prevDate]!==previous.adjclose)reasons.push('PREVIOUS_LATEST_ADJCLOSE_CHANGED_OR_MISSING');
  let anchorFactor:number|null=null,currentFactor:number|null=null;
  if(policy==='INDEX')market.close_attribution_policy='INDEX_ADJCLOSE_ONLY; Close retained as raw provenance';
  else if(oldClose&&positive(oldClose[prevDate])&&positive(closes[prevDate])&&positive(closes[target])) {
    anchorFactor=previous.adjclose/oldClose[prevDate];const newFactor=(prices[prevDate]??previous.adjclose)/closes[prevDate];currentFactor=metrics.adjclose/closes[target];
    if(!closeEnough(anchorFactor,newFactor,0))reasons.push('PREVIOUS_ADJUSTMENT_FACTOR_CHANGED');
    if(!closeEnough(anchorFactor,currentFactor,0))reasons.push('CURRENT_ADJUSTMENT_FACTOR_INCOMPARABLE');
  }else reasons.push('ADJUSTMENT_FACTOR_ANCHOR_MISSING');
  market.adjustment_factor_evidence={previous_anchor_factor:anchorFactor,current_factor:currentFactor};
  const hybrid:Pair[]=pairs.map(([d,p])=>[d,old[d]??p]),counter=calculate(hybrid,target,symbol==='SPCX');
  const prevMap={...old,...Object.fromEntries(pairs.filter(([d])=>d<=prevDate))},prevRecomputed=calculate(Object.entries(prevMap).sort() as Pair[],prevDate,symbol==='SPCX');
  const impacts=impact(counter,metrics);revision.impact_at_current_target=impacts;revision.impact_on_previous_session=impact(previous,prevRecomputed);
  market.old_basis_counterfactual={...view(counter),conditional_only_until_comparability_proven:true};market.previous_recomputed_metrics=view(prevRecomputed);
  market.window_high_expired_naturally=!hybrid.slice(-252).some(([d])=>d===previous.highest_date);
  const touched=unique([...baseline,...confirmed]),transitionPrev={...previous,triggered_thresholds:touched};
  const proposed=transition(transitionPrev,metrics,significant),control=transition(transitionPrev,counter,significant),basis=basisComparison(previous,pairs,touched,significant,symbol==='SPCX'),latest=basis.latest_transition;
  market.same_basis_comparison=basis;market.mixed_basis_event_diagnostic_only=proposed.change_event;
  const deps=dependencies(previous,pairs,context,latest.change_event);market.revision_dependency_assessment=deps;
  if(deps.some(d=>d.classification!=='PROVEN_OUTSIDE_EVENT_WINDOWS'))reasons.push('UNRESOLVED_PRIOR_REVISION_REVIEW');
  market.unrevised_basis_event=control.change_event;market.revised_basis_event=proposed.change_event;
  const actualMove=metrics.adjclose!==prevRecomputed.adjclose,levels=unique([...control.crossed_thresholds_this_run,...latest.crossed_thresholds_this_run,...(actualMove?proposed.crossed_thresholds_this_run:[])]);
  market.old_basis_new_crossings=control.crossed_thresholds_this_run;market.latest_basis_new_crossings=latest.crossed_thresholds_this_run;market.latest_basis_event=latest.change_event;
  if(raw.length) {
    if(maxRel>1e-5)reasons.push('RELATIVE_REVISION_NOT_PRECISION_CANDIDATE');
    if(counter.highest_adjclose!==metrics.highest_adjclose||counter.highest_date!==metrics.highest_date)reasons.push('ROLLING_EXTREMUM_REVISED');
    if(prevRecomputed.highest_adjclose!==previous.highest_adjclose||prevRecomputed.highest_date!==previous.highest_date)reasons.push('PREVIOUS_EXTREMUM_REVISED');
    if(tier(prevRecomputed.drawdown)!==tier(previous.drawdown))reasons.push('PREVIOUS_TIER_REVISED');
    if(proposed.change_event!==control.change_event||!equal(levels,control.crossed_thresholds_this_run)||tier(metrics.drawdown)!==tier(counter.drawdown))reasons.push('COUNTERFACTUAL_EVENT_OR_TIER_DISAGREEMENT');
    if(latest.change_event!==control.change_event||!equal(latest.crossed_thresholds_this_run,control.crossed_thresholds_this_run))reasons.push('SAME_BASIS_CROSSING_DISAGREEMENT');
    const bound=Math.max(Math.abs(metrics.drawdown-counter.drawdown),maxRel*2),margin=Math.min(...(levels.length?levels:[10,20,30]).map(l=>Math.abs(metrics.drawdown+l/100)));
    market.revision_drawdown_error_bound=bound;market.nearest_tested_threshold_margin=margin;
    if(margin<=bound)reasons.push('THRESHOLD_MARGIN_NOT_GREATER_THAN_REVISION_BOUND');
    if(proposed.change_event==='DEEPER_DRAWDOWN'&&Math.abs(((previous.deepening_anchor??previous.drawdown)-metrics.drawdown)*100-significant)<=bound*100)reasons.push('DEEPENING_MARGIN_NOT_GREATER_THAN_REVISION_BOUND');
    revision.classification=!reasons.length?'NUMERIC_PRECISION_CANDIDATE':maxRel>1e-5||impacts.changed.watch_tier?'MATERIAL_REVISION':'REVISION_REVIEW_REQUIRED';revision.requires_review=!!reasons.length;
  }
  revision.risk_reasons=[...reasons];
  const support=new Set([...Object.keys(old).sort().slice(-252),...pairs.slice(-252).map(p=>p[0])]);
  const unrelated=!!raw.length&&raw.every(r=>!support.has(r.date))&&latest.change_event!=='DEEPER_DRAWDOWN';
  if(unrelated){reasons.splice(0,reasons.length,...reasons.filter(r=>!['RELATIVE_REVISION_NOT_PRECISION_CANDIDATE','THRESHOLD_MARGIN_NOT_GREATER_THAN_REVISION_BOUND'].includes(r)));revision.market_dependency='PROVEN_OUTSIDE_EVENT_WINDOWS';}
  market.threshold_proofs={};const soft=new Set(['ROLLING_EXTREMUM_REVISED','PREVIOUS_EXTREMUM_REVISED','PREVIOUS_TIER_REVISED','COUNTERFACTUAL_EVENT_OR_TIER_DISAGREEMENT','SAME_BASIS_CROSSING_DISAGREEMENT','THRESHOLD_MARGIN_NOT_GREATER_THAN_REVISION_BOUND']);
  for(const level of levels) {
    const both=control.crossed_thresholds_this_run.includes(level)&&latest.crossed_thresholds_this_run.includes(level),margin=Math.min(...['old_previous','old_current','latest_previous','latest_current'].map(k=>Math.abs((basis as R)[k].drawdown+level/100))),bound=unrelated?0:Math.max(Math.abs(metrics.drawdown-counter.drawdown),maxRel*2),blockers=policy==='INDEX'?reasons:reasons.filter(r=>!soft.has(r));
    market.threshold_proofs[String(level)]={new_crossing_proven_in_both:both,minimum_margin:margin,revision_error_bound:bound,blockers:[...blockers],can_confirm:newSession&&both&&(!raw.length||unrelated||margin>bound)&&!blockers.length};
  }
  market.comparability_proven=!reasons.length;market.can_confirm=newSession&&!reasons.length;market.candidate_thresholds=levels;market.crossed_thresholds=levels;
  market.significant_deepening=proposed.change_event==='DEEPER_DRAWDOWN';market.recovery=proposed.change_event==='RECOVERY';market.reentry=proposed.change_event==='REENTRY';
  market.event_type=levels.length?(levels.some(l=>!touched.includes(l))?'NEW_THRESHOLD':'REENTRY'):proposed.change_event;
  const candidates:R[]=[];
  const has=!!levels.length||(proposed.change_event!=='NO_CHANGE'&&(!raw.length||actualMove||control.change_event===latest.change_event&&latest.change_event===proposed.change_event));
  if(newSession&&has) {
    if(levels.length)for(const l of levels)candidates.push({symbol,trading_date:target,event_type:'THRESHOLD_CROSSING',event_subtype:touched.includes(l)?'REENTRY':'NEW_THRESHOLD',threshold:l,status:market.threshold_proofs[String(l)].can_confirm?'CONFIRMED':'PENDING_REVIEW',rules_version:RULES});
    else candidates.push({symbol,trading_date:target,event_type:proposed.change_event,event_subtype:proposed.change_event,threshold:null,status:market.can_confirm&&control.change_event===latest.change_event&&latest.change_event===proposed.change_event?'CONFIRMED':'PENDING_REVIEW',rules_version:RULES});
    for(const candidate of candidates)if(context) {const existing=context[await stableId(candidate,policy==='INDEX')];if(existing?.status==='REJECTED')throw Error('REOPEN_REQUIRED');if(existing?.status==='PENDING_REVIEW')candidate.status='PENDING_REVIEW';}
    const statuses=[...new Set(candidates.map(c=>c.status))];market.status=statuses.length===1?statuses[0]:'MIXED_CONFIRMED_PENDING';market.can_confirm=candidates.some(c=>c.status==='CONFIRMED');
  }else if(same)market.event_type='NO_CHANGE';
  const evidence={previous_trading_date:prevDate,previous_adjclose:previous.adjclose,previous_drawdown:previous.drawdown,current_adjclose:metrics.adjclose,current_drawdown:metrics.drawdown,old_basis_counterfactual:market.old_basis_counterfactual,comparability_proven:market.comparability_proven,comparability_reasons:[...reasons],revision_count:raw.length,revision_dates:revision.dates,same_basis_comparison:basis,threshold_proofs:market.threshold_proofs,revision_dependency_assessment:deps};
  for(const c of candidates)c.evidence=clone(evidence);
  const confirmedNow=candidates.filter(c=>c.threshold!==null&&c.status==='CONFIRMED').map(c=>c.threshold).sort((a,b)=>a-b),pendingNow=candidates.filter(c=>c.threshold!==null&&c.status==='PENDING_REVIEW').map(c=>c.threshold).sort((a,b)=>a-b);
  confirmed=unique([...confirmed,...confirmedNow]);ts.confirmed=confirmed;market.confirmed_thresholds_this_run=confirmedNow;market.pending_thresholds_this_run=pendingNow;
  const summary=candidates.length?(market.status==='CONFIRMED'?proposed.change_event:'PENDING_REVIEW'):raw.length?'HISTORICAL_REVISION':'NO_CHANGE';
  let anchor=previous.deepening_anchor??previous.drawdown;
  if(!['NO_CHANGE','PENDING_REVIEW'].includes(summary))anchor=candidates.length&&candidates.every(c=>c.status==='CONFIRMED')?metrics.drawdown:anchor+prevRecomputed.drawdown-previous.drawdown;
  const fresh=confirmedNow.filter(l=>!touched.includes(l));
  return {...depth(previous,metrics,market.event_type,market.status,prevRecomputed),latest_basis_daily_drawdown_change_pp:(metrics.drawdown-prevRecomputed.drawdown)*100,...metrics,revision_observation:revision,market_observation:market,threshold_state:ts,market_events:candidates,change_event:summary,watch_tier:tier(metrics.drawdown),previous_watch_tier:previous.watch_tier,crossed_thresholds_this_run:confirmedNow,new_thresholds:fresh,reentered_thresholds:confirmedNow.filter(l=>touched.includes(l)),triggered_thresholds:confirmed,confirmed_thresholds:confirmed,baseline_observed_thresholds:baseline,last_new_trigger_date:fresh.length?target:previous.last_new_trigger_date??null,deepening_anchor:anchor,raw_revision_differences:raw};
}
