import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {changes,aggregate,allocate} from '../lib/domain.ts';
const position=(key,value,shares,kind='EQUITY',ticker=key)=>({key,cusip:key,name:key,class:'COM',kind,value,shares,ticker});
const snapshot=(period,positions)=>({period,positions,complete:true,totalValue:positions.reduce((s,p)=>s+p.value,0),sourceUrl:'https://www.sec.gov/test',filedAt:'2026-08-14',accession:'test'});
const fund=(id,old,current)=>({id,name:id,status:'ready',snapshots:[snapshot('2026-03-31',old),snapshot('2026-06-30',current)]});
const dataset=funds=>({period:'2026-06-30',previousPeriod:'2026-03-31',funds});
test('Share deltas classify exits and additions, not mark-to-market gains',()=>{
 const d=changes(snapshot('2026-06-30',[position('A',200,10),position('C',30,3)]),snapshot('2026-03-31',[position('A',100,10),position('B',40,4)]));
 assert.equal(d.find(r=>r.key==='A').movement,'unchanged');assert.equal(d.find(r=>r.key==='B').movement,'closed');assert.equal(d.find(r=>r.key==='B').estimatedChange,-40);assert.equal(d.find(r=>r.key==='C').movement,'new');
});
test('Missing previous snapshot cannot be treated as a liquidation',()=>assert.throws(()=>changes({...snapshot('a',[]),complete:false},snapshot('b',[])),/Incomplete/));
test('Equal fund weights include non-holding funds in denominator',()=>{
 const d=dataset([fund('large',[],[position('A',900,9),position('B',100,1)]),fund('small',[],[position('B',10,1)])]);
 const equal=aggregate(d,['large','small']);assert.equal(equal.find(r=>r.key==='A').weight,.45);assert.equal(equal.find(r=>r.key==='B').weight,.55);
 assert.ok(Math.abs(aggregate(d,['large','small'],'value').find(r=>r.key==='A').weight-900/1010)<1e-12);
});
test('Excluding a fund recomputes holdings, deltas, and weights',()=>{const d=dataset([fund('one',[],[position('A',100,1)]),fund('two',[],[position('B',100,1)])]);assert.deepEqual(aggregate(d,['one']).map(r=>r.key),['A']);assert.equal(aggregate(d,[]).length,0)});
test('PUT positions stay separate and are not subtracted from equity longs',()=>{const d=dataset([fund('a',[],[position('X',100,1),position('X:PUT',70,3,'PUT')])]);assert.equal(aggregate(d,['a'])[0].value,100);assert.equal(aggregate(d,['a'],'equal','PUT')[0].value,70)});
test('A fund can buy while another sells: both counts and exit retained',()=>{const d=dataset([fund('a',[position('A',100,10)],[position('A',150,15)]),fund('b',[position('A',100,10)],[])]);const r=aggregate(d,['a','b'])[0];assert.equal(r.buyers,1);assert.equal(r.sellers,1);assert.equal(r.holders,1);assert.equal(r.funds.find(f=>f.fundId==='b').movement,'closed')});
test('Caps retain cash and never exceed budget',()=>{const rows=aggregate(dataset([fund('a',[],[position('A',100,10),position('B',100,10)])]),['a']);const p=allocate(rows,1000,.2,.1,8);assert.equal(p.positions.length,2);assert.equal(p.cash,600);assert.ok(p.positions.every(p=>p.weight<=.2));assert.equal(p.positions.reduce((s,p)=>s+p.amount,0)+p.cash,1000)});
test('No eligible securities means 100% cash; invalid controls fail',()=>{assert.equal(allocate([],1000,.2,.1,8).cash,1000);for(const args of [[0,.2,.1,8],[100,0,.1,8],[100,.2,1,8],[100,.2,.1,0],[NaN,.2,.1,8]])assert.throws(()=>allocate([],...args))});
test('Options, unverified tickers and exited securities cannot enter target allocation',()=>{const d=dataset([fund('a',[position('EXIT',100,10)],[position('NO',100,10,'EQUITY',null),position('P',100,10,'PUT')])]);assert.equal(allocate(aggregate(d,['a']),1000,.2,.1,8).positions.length,0)});
test('Real filing pairs reconcile, identity-correct, and combined weights sum to one',()=>{
 const d=JSON.parse(readFileSync(new URL('../data/filings.json',import.meta.url),'utf8'));const ready=d.funds.filter(f=>f.status==='ready');assert.ok(ready.length>=8);assert.equal(d.funds.find(f=>f.id==='lonepine').cik,'1061165');assert.equal(d.funds.find(f=>f.id==='duquesne').status,'unavailable');
 for(const f of ready)for(const s of f.snapshots){assert.ok(Math.abs(s.positions.reduce((v,p)=>v+p.value,0)-s.totalValue)<1);assert.equal(new Set(s.positions.map(p=>p.key)).size,s.positions.length);assert.ok(s.positions.every(p=>Number.isFinite(p.value)&&p.value>=0))}
 for(const mode of ['equal','value']){const r=aggregate(d,ready.map(f=>f.id),mode);assert.ok(Math.abs(r.reduce((s,p)=>s+p.weight,0)-1)<1e-8)}
});
