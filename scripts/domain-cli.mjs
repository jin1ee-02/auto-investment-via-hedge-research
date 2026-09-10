import {readFileSync} from 'node:fs';
import {aggregate,allocate,researchCandidates} from '../lib/domain.ts';
const input=JSON.parse(readFileSync(0,'utf8'));
const dataset=JSON.parse(readFileSync(new URL('../data/filings.json',import.meta.url),'utf8'));
if(!Array.isArray(input.fundIds)||!input.fundIds.length||new Set(input.fundIds).size!==input.fundIds.length||!input.fundIds.every(id=>dataset.funds.some(f=>f.id===id&&f.status==='ready')))throw Error('Select available funds with complete filing pairs');
const rows=aggregate(dataset,input.fundIds,'equal','EQUITY');
if(input.action==='candidates')process.stdout.write(JSON.stringify({period:dataset.period,previousPeriod:dataset.previousPeriod,generatedAt:dataset.generatedAt,rows:researchCandidates(rows,input.count)}));
else if(input.action==='allocate'){
 const scored=researchCandidates(rows,input.count).filter(r=>r.buyers>=2&&r.buyers>r.sellers&&Object.hasOwn(input.scores,r.ticker)).map(r=>{const score=input.scores[r.ticker];if(typeof score!=='number'||!Number.isFinite(score)||score<0||score>100)throw Error('Invalid AI score');return {...r,score}});
 process.stdout.write(JSON.stringify(allocate(scored,input.budget,input.cap,input.cash,input.count)));
}else throw Error('Unknown domain action');
