import test from 'node:test';
import assert from 'node:assert/strict';
import {riskPlan} from '../lib/swing.ts';
test('risk sizing respects both cash and loss budgets',()=>{
 assert.deepEqual(riskPlan(100,95,110,1000,20),{quantity:4,amount:400,maxLoss:20,rewardRisk:2});
 assert.equal(riskPlan(100,95,110,100,20).quantity,1);
 assert.equal(riskPlan(100,100,110,1000,20),null);
 assert.equal(riskPlan(100,95,90,1000,20),null);
 assert.equal(riskPlan(Infinity,95,110,1000,20),null);
});
