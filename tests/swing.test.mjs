import test from 'node:test';
import assert from 'node:assert/strict';
import {reviewMarket,riskPlan} from '../lib/swing.ts';
test('risk sizing respects both cash and loss budgets',()=>{
 assert.deepEqual(riskPlan(100,95,110,1000,20),{quantity:4,amount:400,maxLoss:20,rewardRisk:2});
 assert.equal(riskPlan(100,95,110,100,20).quantity,1);
 assert.equal(riskPlan(100,100,110,1000,20),null);
 assert.equal(riskPlan(100,95,90,1000,20),null);
 assert.equal(riskPlan(Infinity,95,110,1000,20),null);
});
test('unavailable and stale evidence never becomes a trend confirmation',()=>{
 const now=Date.parse('2026-09-12T12:00:00Z');
 const m={status:'ready',asOf:'2026-09-11',close:110,sma20:100,sma50:95,relativeReturn20:.03};
 assert.equal(reviewMarket(3,1,m,now),'추세 확인 · 촉매 조사');
 assert.equal(reviewMarket(3,1,{...m,asOf:'2026-09-01'},now),'데이터 재확인');
 assert.equal(reviewMarket(3,1,{...m,status:'limited'},now),'데이터 재확인');
 assert.equal(reviewMarket(1,3,m,now),'매도 우세 · 위험 점검');
 assert.equal(reviewMarket(3,1,{...m,close:90},now),'가격 흐름 대기');
});
