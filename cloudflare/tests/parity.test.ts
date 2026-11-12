import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {evaluate} from '../src/observations.ts';
import {stableId,RecordValue,calendar,latestSession,calculate,fsum,semanticJson,sha} from '../src/core.ts';
import {validateYahoo} from '../src/yahoo.ts';
import {pythonPriceFingerprint} from '../src/storage.ts';
import {writeTestResult} from './test-output.ts';
const load=(name:string)=>JSON.parse(readFileSync(new URL('../fixtures/'+name,import.meta.url),'utf8'));
const cases=load('golden.json'),validation=load('validation.json');
const results:any[]=[];let floats=0,maxAbs=0;
// Only numerical fields permit tolerance. Enum decisions, dates, levels, IDs,
// booleans, nulls, key sets and array cardinality must match exactly.
function compare(actual:any,expected:any,path='') {
  if(typeof expected==='number') {
    assert.equal(typeof actual,'number',path);assert.ok(Number.isFinite(actual),path);
    const discrete=/threshold|samples|count|warmup|revision_dates/.test(path)&&!path.includes('margin')&&!path.includes('bound');
    if(discrete)assert.equal(actual,expected,path);
    else {const delta=Math.abs(actual-expected);maxAbs=Math.max(maxAbs,delta);floats++;assert.ok(delta<=Math.max(1e-12,Math.abs(expected)*1e-12),`${path}: ${actual} != ${expected}`);}
  }else if(Array.isArray(expected)) {
    assert.ok(Array.isArray(actual),path);assert.equal(actual.length,expected.length,path);expected.forEach((v,i)=>compare(actual[i],v,path+'/'+i));
  }else if(expected&&typeof expected==='object') {
    assert.deepEqual(Object.keys(actual).sort(),Object.keys(expected).sort(),path);for(const k of Object.keys(expected))compare(actual[k],expected[k],path+'/'+k);
  }else assert.equal(actual,expected,path);
}
for(const c of cases)test('golden '+c.name,async()=> {
  const i=c.input;let model:any,error:string|undefined;
  assert.equal(pythonPriceFingerprint(Object.fromEntries(i.pairs)),i.normalized_price_fingerprint,'normalized Python float64 price-map hash');
  try{model=await evaluate(i.symbol,i.pairs,i.closes,i.identity,i.previous,1,i.context,i.policy);}catch(e){error=String((e as Error).message).split(':')[0];}
  if(c.expected.error)assert.equal(error,c.expected.error);else {
    assert.equal(error,undefined);compare(model,c.expected.model);
    assert.deepEqual(await Promise.all(model.market_events.map((e:RecordValue)=>stableId(e,i.policy==='INDEX'))),c.expected.event_ids);
  }
  results.push({name:c.name,status:'PASS'});
});
for(const c of validation)test('Yahoo '+c.name,()=> {
  if(c.pass) {const s=validateYahoo(c.symbol,c.raw,c.asof);assert.equal(s.target,c.target);assert.deepEqual(s.pairs,c.pairs);}
  else assert.throws(()=>validateYahoo(c.symbol,c.raw,c.asof));
});
test('calendar exhaustive UTC close boundaries and DST',()=> {
  for(const [date,bounds] of Object.entries(calendar))if(bounds) {assert.equal(latestSession(bounds[1]),date);if(date>'2024-01-02')assert.notEqual(latestSession(bounds[1]-1),date);}
  assert.equal(new Date(calendar['2026-03-06']![1]).getUTCHours(),21);
  assert.equal(new Date(calendar['2026-03-09']![1]).getUTCHours(),20);
  assert.equal(new Date(calendar['2026-11-27']![1]).getUTCHours(),18);
  // The guard applies to New York date, as in Python, rather than UTC date.
  assert.throws(()=>latestSession('2029-01-01T12:00:00Z'));
  assert.throws(()=>latestSession('2026-11-06T12:00:00'));
});
test('finite input guard and compensated cancellation',()=> {
  assert.equal(fsum([1e16,1,-1e16]),1);
  for(const n of [NaN,Infinity,-Infinity,0,-1,true])assert.throws(()=>calculate([['2026-11-06',n as number]],'2026-11-06',true));
  assert.throws(()=>semanticJson(NaN));
});
test('sha256 known vector',async()=>assert.equal(await sha('abc'),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'));
test('write parity evidence',()=> {
  writeTestResult('parity_results.json',{golden_fixtures:cases.length,validation_fixtures:validation.length,passed:results.length,compared_float_fields:floats,max_absolute_difference:maxAbs,tolerance:{absolute:1e-12,relative:1e-12},event_ids:'EXACT',discrete_fields:'EXACT',results});
});
