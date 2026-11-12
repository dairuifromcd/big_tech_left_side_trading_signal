import {latestSession,missing} from './core.ts';
import {digest} from './storage.ts';
export function gapPlan(previous:string,target:string) {
  const gaps=missing(previous,target);
  return {status:gaps.length?'CATCHUP_REQUIRED':'NO_GAP',missing_sessions:gaps,required_processing_order:gaps.length?[...gaps,target]:[],later_history_origin:'RECONSTRUCTED_CATCHUP',event_status:gaps.length?'PENDING_REVIEW':null,automatic_apply:'BLOCKED',state_updated:false};
}
export function validateArchive(raw:string,hash:string,requestEnd:string,declaredAsOf:string,attestation:string) {
  if(!attestation.trim()||!requestEnd||digest(raw)!==hash)throw Error('ARCHIVE_PROVENANCE_REQUIRED');
  const original=Date.parse(requestEnd),declared=Date.parse(declaredAsOf);
  // latestSession requires aware timestamps and the same bounded calendar.
  if(!Number.isFinite(original)||!Number.isFinite(declared)||Math.abs(original-declared)>60000||latestSession(requestEnd)!==latestSession(declaredAsOf))throw Error('RECONSTRUCTED_CATCHUP');
  return {origin:'TRUSTED_ARCHIVE',automatic_apply:false,point_in_time_independently_authenticated:false,operator_attestation:attestation,original_capture_utc:requestEnd};
}
