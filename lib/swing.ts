export function riskPlan(entry:number,stop:number,target:number,budget:number,risk:number){
 if(![entry,stop,target,budget,risk].every(v=>Number.isFinite(v)&&v>0)||stop>=entry||target<=entry||risk>budget)return null;
 const perShare=entry-stop,quantity=Math.floor(Math.min(budget/entry,risk/perShare));
 return {quantity,amount:quantity*entry,maxLoss:quantity*perShare,rewardRisk:(target-entry)/perShare};
}
