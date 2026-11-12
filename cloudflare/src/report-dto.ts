// Independent public contract; internal state/evidence types must never be returned.
export type EventStatus='CONFIRMED'|'PENDING_REVIEW'|'REJECTED';
export interface ReportEnvelope<T> {
  schema_version:'report-v1';mode:'DRY_RUN_MOCK_OFFLINE';data_version:number;updated_at:number|null;data:T;
}
export interface MetricDTO {
  adjclose:number;highest_adjclose:number;highest_date:string;drawdown:number;
  rsi14:number|null;sma50:number|null;sma200:number|null;window_samples:number;
}
export interface AssetDTO {
  symbol:string;category:'stocks'|'indices';trading_date:string;metrics:MetricDTO;
  watch_tier:'NONE'|'WATCH_10'|'WATCH_20'|'WATCH_30';data_quality:'PASS'|'PASS_PROVISIONAL';
  confirmed_thresholds:number[];pending_event_ids:string[];daily_drawdown_change_pp:number|null;
  daily_new_deepening:boolean;cumulative_anchor_deepening_pp:number|null;
  last_candidate_type:string;last_candidate_status:EventStatus|'NO_EVENT'|'MIXED_CONFIRMED_PENDING';
  source_captured_at:string;origin:'MOCK_OFFLINE';rules_version:string;
}
export interface EventDTO {
  event_id:string;symbol:string;trading_date:string;event_type:string;event_subtype:string|null;
  threshold:number|null;status:EventStatus;evidence_version_count:number;dependency_review_required:boolean;
}
export interface PageDTO<T> {items:T[];next_cursor:string|null}
// Future historical analysis series must retain capture_date separately from bar_date.
// Analysis from a later snapshot is never a Point-in-Time event or a backfill receipt.
export interface HistoricalAnalysisPointDTO {
  bar_date:string;capture_date:string;metrics:MetricDTO;
  origin:'LATEST_VALIDATED_SNAPSHOT_ANALYSIS';point_in_time_capture:false;
}
