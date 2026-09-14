export type MarketSnapshot={key:string;ticker:string;status:'ready'|'limited'|'unavailable';asOf?:string;close?:number;sma20?:number;sma50?:number;return20?:number;relativeReturn20?:number|null;relativeVolume?:number;dataGaps:string[];sourceUrl:string};
export function reviewMarket(buyers:number,sellers:number,market?:MarketSnapshot,now=Date.now()){
 if(!market)return '가격 점검 필요';
 const age=market.asOf?(now-Date.parse(market.asOf+'T00:00:00Z'))/86400000:Infinity;
 if(market.status!=='ready'||!Number.isFinite(age)||age>5||age<0)return '데이터 재확인';
 if(sellers>=buyers)return sellers===buyers?'의견 대립 · 관찰':'매도 우세 · 위험 점검';
 if(market.close!>market.sma20!&&market.close!>market.sma50!&&market.relativeReturn20!>0)return '추세 확인 · 촉매 조사';
 return '가격 흐름 대기';
}
export function riskPlan(entry:number,stop:number,target:number,budget:number,risk:number){
 if(![entry,stop,target,budget,risk].every(v=>Number.isFinite(v)&&v>0)||stop>=entry||target<=entry||risk>budget)return null;
 const perShare=entry-stop,quantity=Math.floor(Math.min(budget/entry,risk/perShare));
 return {quantity,amount:quantity*entry,maxLoss:quantity*perShare,rewardRisk:(target-entry)/perShare};
}
