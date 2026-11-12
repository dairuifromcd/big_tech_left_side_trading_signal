import {Store,reportAsset,category} from './storage.ts';
import {SYMBOLS,RecordValue as R,checkDate} from './core.ts';
const headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'};
export function api(store:Store,request:Request) {
  if(request.method!=='GET')return Response.json({error:'READ_ONLY'}, {status:405,headers:{...headers,Allow:'GET'}});
  try {
    store.guard();const url=new URL(request.url),path=url.pathname;
    const latest=store.q('SELECT * FROM runs ORDER BY date DESC LIMIT 1')[0]??null;
    const envelope=(data:any)=>Response.json({schema_version:'report-v1',mode:'DRY_RUN_MOCK_OFFLINE',data_version:store.q('SELECT COALESCE(SUM(version),0) AS version FROM states')[0].version,updated_at:latest?.updated??null,data}, {headers});
    const pagination=()=> {
      const limit=Number(url.searchParams.get('limit')??50),offset=Number(url.searchParams.get('cursor')??0);
      if(!Number.isInteger(limit)||limit<1||limit>200||!Number.isInteger(offset)||offset<0||offset>100000)throw Error('BAD_PAGINATION');
      const from=url.searchParams.get('from')??'2024-01-01',to=url.searchParams.get('to')??'2028-12-31';checkDate(from);checkDate(to);if(from>to)throw Error('BAD_RANGE');return {limit,offset,from,to};
    };
    const page=(rows:any[],limit:number,offset:number)=>({items:rows.slice(offset,offset+limit),next_cursor:rows.length>offset+limit?String(offset+limit):null});
    if(path==='/api/overview')return envelope(SYMBOLS.map(symbol=>{const state=store.state(symbol);return state?{...reportAsset(state.doc),state_version:state.version}:{symbol,status:'NO_COMMITTED_BASELINE'};}));
    if(path==='/api/runs/latest')return envelope(latest?{...latest,tasks:store.q('SELECT symbol,status,started,error FROM claims WHERE date=? ORDER BY ordinal',latest.date)}:null);
    if(path==='/api/health')return envelope({latest_run:latest,calendar_expires:'2028-12-31',calendar_update_due:'2028-07-01',calendar_warning:Date.now()>=Date.parse('2028-07-01T00:00:00Z'),cloud_runtime:'NOT_VERIFIED',backup_count:store.q('SELECT COUNT(*) AS n FROM backups')[0].n,resource_usage:'NOT_VERIFIED',pending_count:store.q('SELECT * FROM events').map(r=>store.unpack(r)).filter(e=>e.status==='PENDING_REVIEW').length});
    if(path==='/api/events') {
      const {limit,offset,from,to}=pagination(),symbol=url.searchParams.get('symbol'),status=url.searchParams.get('status');
      if(symbol&&!SYMBOLS.includes(symbol))return Response.json({error:'UNKNOWN_SYMBOL'},{status:404,headers});
      if(status&&!['CONFIRMED','PENDING_REVIEW','REJECTED'].includes(status))throw Error('BAD_STATUS');
      const rows=store.q('SELECT * FROM events ORDER BY id').map(r=>store.unpack(r)).filter(e=>(!symbol||e.symbol===symbol)&&(!status||e.status===status)&&e.trading_date>=from&&e.trading_date<=to).map(e=>({event_id:e.event_id,symbol:e.symbol,trading_date:e.trading_date,event_type:e.event_type,event_subtype:e.event_subtype??null,threshold:e.threshold,status:e.status,evidence_version_count:e.evidence_versions.length,dependency_review_required:e.dependency_review_required??false}));return envelope(page(rows,limit,offset));
    }
    const match=path.match(/^\/api\/assets\/([^/]+)(\/history)?$/);
    if(match) {
      const symbol=decodeURIComponent(match[1]);if(!SYMBOLS.includes(symbol))return Response.json({error:'UNKNOWN_SYMBOL'},{status:404,headers});
      if(!match[2]){const state=store.state(symbol);return state?envelope({...reportAsset(state.doc),state_version:state.version}):Response.json({error:'NO_COMMITTED_STATE'},{status:404,headers});}
      const {limit,offset,from,to}=pagination();
      // Committed report history is Point-in-Time mock history, not a fabricated
      // capture for every old bar in a later Yahoo response.
      const rows=store.q('SELECT body,hash,version FROM history WHERE category=? AND symbol=? AND date>=? AND date<=? ORDER BY date,version',category(symbol),symbol,from,to).map(r=>store.unpack(r));return envelope(page(rows,limit,offset));
    }
    return Response.json({error:'NOT_FOUND'},{status:404,headers});
  }catch(e){const message=String((e as Error).message),bad=/BAD_|CALENDAR_OUT/.test(message);return Response.json({error:bad?'BAD_QUERY':'STATE_ERROR'},{status:bad?400:503,headers});}
}
