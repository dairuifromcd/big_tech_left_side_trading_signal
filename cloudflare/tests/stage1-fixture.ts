// Local security probes only. No credential values or test RPCs enter deployment sources.
export const OBJECT_NAME='phase51b-synthetic-20261113-v1';
export const STAGE1='EXPLICIT_PHASE51B_IDENTITY_V1';
export const REPORT_PATHS=['/api/overview','/api/runs/latest','/api/health','/api/events','/api/assets/NVDA','/api/assets/NVDA/history'];
export function windowBindings(start:number) {
  return {REMOTE_MOCK_ENABLED:STAGE1,MOCK_START_UTC:new Date(start).toISOString(),
    MOCK_END_UTC:new Date(start+86400000).toISOString(),MOCK_INIT_END_UTC:new Date(start+1200000).toISOString()};
}
export function probes(control:string,report:string) {
  return [
    {name:'missing authorization',path:'/_mock/identity',status:403},
    {name:'wrong authorization',path:'/_mock/identity',token:'wrong',status:403},
    {name:'report cannot control identity',path:'/_mock/identity',token:report,status:403},
    {name:'malformed bearer',path:'/_mock/identity',rawAuthorization:control,status:403},
    ...['object_id=arbitrary','namespace=arbitrary','token=arbitrary','fixture_date=2026-11-06','sql=DROP%20TABLE%20meta']
      .map(query=>({name:'identity rejects query '+query,path:'/_mock/identity?'+query,token:control,status:403})),
    {name:'identity refuses POST',path:'/_mock/identity',method:'POST',token:control,status:405},
    ...[
      {path:'/_mock/initialize',body:{operation:'INITIALIZE_EMPTY_ISOLATED_MOCK'}},
      {path:'/_mock/start',body:{fixture_date:'2026-11-06'}},
      {path:'/_mock/start',body:{fixture_date:'2099-01-01'}},
      {path:'/_mock/stop',body:{}},
      {path:'/_mock/sql',body:{sql:'CREATE TABLE injected(x)'}},
      {path:'/_mock/objects/arbitrary/start',body:{fixture_date:'2026-11-06'}},
    ].map(p=>({...p,name:'Stage1 refuses '+p.path+' '+JSON.stringify(p.body),method:'POST',token:control,status:403})),
    {name:'status denied',path:'/_mock/status',token:control,status:403},
    {name:'status unauthorized',path:'/_mock/status',status:403},
    ...REPORT_PATHS.map(path=>({name:'report denied '+path,path,token:report,status:403})),
    {name:'report unauthorized',path:'/api/overview',status:401},
    {name:'control cannot report',path:'/api/overview',token:control,status:401},
    {name:'report write denied',path:'/api/overview',method:'POST',token:report,body:{},status:405},
    {name:'unknown admin denied',path:'/_mock/unknown',token:control,status:403},
  ];
}
export function request(p:ReturnType<typeof probes>[number]) {
  return new Request('https://stage1.invalid'+p.path,{method:p.method??'GET',
    headers:p.rawAuthorization?{Authorization:p.rawAuthorization}:p.token?{Authorization:'Bearer '+p.token}:{},
    ...('body' in p?{body:JSON.stringify(p.body)}:{})});
}
