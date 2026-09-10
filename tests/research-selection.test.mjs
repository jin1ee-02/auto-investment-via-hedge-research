import test from 'node:test';
import assert from 'node:assert/strict';
import {researchCandidates,buyResearchCandidates,activityConsensus} from '../lib/domain.ts';
import {filingCalendar} from '../lib/filing-calendar.ts';
test('Browse all candidates beyond 20 while automatic research stays bounded',()=>{
 const rows=Array.from({length:35},(_,i)=>({kind:'EQUITY',key:String(i).padStart(2,'0'),ticker:'T'+i,buyers:2,sellers:0,holders:2}));
 assert.equal(researchCandidates(rows).length,35);
 assert.equal(researchCandidates(rows).slice(32,40).length,3);
 assert.equal(researchCandidates(rows,8).length,8);
 assert.throws(()=>researchCandidates(rows,21));
});
test('Research excludes one-sided single participants/options/unresolved tickers and deduplicates',()=>{
 const row={kind:'EQUITY',ticker:'A',holders:2,buyers:2,sellers:0,score:60,key:'a'};
 const picks=researchCandidates([row,{...row,key:'duplicate'},{...row,key:'b',ticker:'B',score:50},{...row,key:'single',ticker:'S',buyers:1,sellers:1,score:100},{...row,key:'option',kind:'PUT',score:100},{...row,key:'unknown',ticker:null,score:100}],2);
 assert.deepEqual(picks.map(r=>r.ticker),['A','B']);
 assert.deepEqual(researchCandidates([{...row,holders:20,buyers:0,sellers:0}]),[]);
});
test('Ranks same-direction activity then agreement; exits and mixed signals are not buy allocations',()=>{
 const base={kind:'EQUITY',holders:4,weight:0.1,score:100};
 const rows=[{...base,key:'buy',ticker:'BUY',buyers:3,sellers:0},{...base,key:'mixed',ticker:'MIX',buyers:3,sellers:3},{...base,key:'exit',ticker:'EXIT',holders:0,buyers:0,sellers:4},{...base,key:'weaker',ticker:'WEAK',buyers:2,sellers:0}];
 assert.deepEqual(researchCandidates(rows).map(r=>r.ticker),['EXIT','BUY','MIX','WEAK']);
 assert.deepEqual(buyResearchCandidates(rows,3).map(r=>r.ticker),['BUY']);
 assert.equal(activityConsensus(rows[1]).direction,'mixed');
 assert.equal(activityConsensus(rows[1]).agreement,0.5);
});
test('Quarter labels, year rollover and SEC holiday-adjusted deadlines',()=>{
 assert.equal(filingCalendar('2026-06-30').deadline,'2026-11-16');
 assert.equal(filingCalendar('2026-09-30').deadline,'2027-02-16');
 assert.equal(filingCalendar('2026-12-31').nextPeriod,'2027-03-31');
 assert.equal(filingCalendar('2030-06-30').deadline,null);
 assert.throws(()=>filingCalendar('2026-06-15'));
});
