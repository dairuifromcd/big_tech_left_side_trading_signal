"""Read-only gap plan; later snapshots are reconstruction, never Point-in-Time."""
from pathlib import Path
import datetime as dt
import market_calendar as calendar
from src import monitor, observations, state


def validate_archive(stock, diagnostic):
    """Do not trust a backdated row-as_of when original capture time is later."""
    if not diagnostic.get('request_end_utc'):
        raise ValueError('ARCHIVE_PROVENANCE_REQUIRED: original per-symbol capture time missing')
    original=dt.datetime.fromisoformat(diagnostic['request_end_utc'])
    declared=dt.datetime.fromisoformat(stock['as_of_utc'])
    if (original.utcoffset() is None or declared.utcoffset() is None or abs((original-declared).total_seconds())>60
            or calendar.latest_completed_session(original)!=calendar.latest_completed_session(declared)):
        raise ValueError('RECONSTRUCTED_CATCHUP: declared history date is not supported by original capture time; automatic apply blocked')
    return {'basis':'Local original capture time + normalized file hash; operator must verify archive trust',
            'original_capture_utc':original.isoformat(),'point_in_time_independently_authenticated':False}


def plan(input_path, state_path):
    previous=state.load(state_path)
    evidence,diagnostics=monitor.read_input(Path(input_path))
    rows=[]
    for symbol in state.SYMBOLS:
        old=previous['stocks'].get(symbol)
        try:
            complete,target,_,_=monitor.validated_prices(symbol,evidence['stocks'][symbol],diagnostics[symbol])
            missing=observations.missing_sessions(old['trading_date'],target) if old else []
            rows.append({'symbol':symbol,'previous_date':old['trading_date'] if old else None,'target':target,
                'missing_sessions':missing,'required_processing_order':missing+[target] if missing else [],
                'source_capture_utc':evidence['stocks'][symbol]['as_of_utc'],
                'mode':'RECONSTRUCTED_CATCHUP' if missing else 'NO_GAP',
                'status':'PENDING_REVIEW' if missing else 'NO_GAP',
                'automatic_apply':'BLOCKED' if missing else 'NOT_NEEDED'})
        except (ValueError,KeyError,TypeError) as exc:
            rows.append({'symbol':symbol,'status':'DATA_ERROR','error':str(exc),'automatic_apply':'BLOCKED'})
    return {'mode':'READ_ONLY_CATCHUP_PLAN','state_updated':False,'stocks':rows,
        'catchup_safety':'BLOCKED','reason':'No automatic Point-in-Time reconstruction or inference of trusted capture history.',
        'manual_steps':[
            'Preserve current checkpoint and audit/backup files; do not delete or change its trading date.',
            'If the primary is missing, list validated backups then explicitly restore a selected checkpoint; never reinitialize.',
            'Provide complete, original, hash-verified archived snapshots for each missing session in order, with verifiable capture provenance.',
            'For each trusted archived session run the normal monitor on an isolated copy with mode ARCHIVED_CATCHUP; inspect report then advance the next session.',
            'If only later-captured prices exist, this plan labels them RECONSTRUCTED_CATCHUP/PENDING_REVIEW and does not mutate state or confirm any event.',
            'After interruption, read last successful date and stable IDs, then resume with the next archived session; same-day reruns are idempotent.',
            'Do not resume unattended operation unless missing dates and evidence attribution have been explicitly resolved.']}
