export type Position={key:string;cusip:string;name:string;class:string;kind:string;value:number;shares:number;ticker:string|null;issuerCik?:string};
export type Snapshot={period:string;filedAt:string;accession:string;sourceUrl:string;totalValue:number;positions:Position[];complete:boolean};
export type Fund={id:string;name:string;cik:string;secName?:string;popular?:boolean;style:string;hedgefollow:string;status:string;error?:string;snapshots:Snapshot[]};
export type Dataset={schemaVersion:number;generatedAt:string;period:string;previousPeriod:string;source:string;universeStatus:string;funds:Fund[]};
export type Movement='new'|'increased'|'decreased'|'closed'|'unchanged';
export type Contribution={fundId:string;fundName:string;value:number;weight:number;previousWeight:number;shares:number;previousShares:number;deltaShares:number;movement:Movement;estimatedChange:number;sourceUrl:string;previousSourceUrl:string};
export type Aggregate=Position & {funds:Contribution[];weight:number;holders:number;buyers:number;sellers:number;addedValue:number;reducedValue:number;score:number};
export function changes(current:Snapshot,previous:Snapshot):Array<Position & {previousShares:number;deltaShares:number;previousWeight:number;weight:number;movement:Movement;estimatedChange:number}>{
 if(!current.complete||!previous.complete)throw Error('Incomplete snapshots cannot be compared');
 const now=new Map(current.positions.map(p=>[p.key,p])),old=new Map(previous.positions.map(p=>[p.key,p]));
 const total=current.positions.filter(p=>p.kind==='EQUITY').reduce((s,p)=>s+p.value,0),priorTotal=previous.positions.filter(p=>p.kind==='EQUITY').reduce((s,p)=>s+p.value,0);
 return [...new Set([...now.keys(),...old.keys()])].map(key=>{const n=now.get(key),p=old.get(key),base=n||p!;const shares=n?.shares||0,previousShares=p?.shares||0,deltaShares=shares-previousShares;
 const movement:Movement=!p?'new':!n?'closed':deltaShares>0?'increased':deltaShares<0?'decreased':'unchanged';
 return {...base,value:n?.value||0,shares,previousShares,deltaShares,weight:total?(n?.value||0)/total:0,previousWeight:priorTotal?(p?.value||0)/priorTotal:0,movement,estimatedChange:deltaShares*(n&&n.shares?n.value/n.shares:p&&p.shares?p.value/p.shares:0)};});
}
export function aggregate(dataset:Dataset,ids:string[],mode:'equal'|'value'='equal',kind='EQUITY'):Aggregate[]{
 const funds=dataset.funds.filter(f=>ids.includes(f.id)&&f.status==='ready'&&[dataset.period,dataset.previousPeriod].every(p=>f.snapshots.some(s=>s.period===p&&s.complete)));
 const rows=new Map<string,Aggregate>();let total=0;
 for(const fund of funds){const now=fund.snapshots.find(s=>s.period===dataset.period)!,old=fund.snapshots.find(s=>s.period===dataset.previousPeriod)!;
 const instrumentTotal=now.positions.filter(p=>p.kind===kind).reduce((s,p)=>s+p.value,0);const priorInstrumentTotal=old.positions.filter(p=>p.kind===kind).reduce((s,p)=>s+p.value,0);const previousPositions=new Map(old.positions.map(p=>[p.key,p]));total+=instrumentTotal;
 for(const change of changes(now,old).filter(p=>p.kind===kind)){
 const weight=instrumentTotal?change.value/instrumentTotal:0;
 if(!rows.has(change.key))rows.set(change.key,{...change,value:0,shares:0,funds:[],weight:0,holders:0,buyers:0,sellers:0,addedValue:0,reducedValue:0,score:0});
 const row=rows.get(change.key)!;row.value+=change.value;row.shares+=change.shares;row.weight+=weight/funds.length;
 if(change.shares>0)row.holders++;if(change.deltaShares>0)row.buyers++;if(change.deltaShares<0)row.sellers++;
 row.addedValue+=Math.max(0,change.estimatedChange);row.reducedValue+=Math.max(0,-change.estimatedChange);
 row.funds.push({fundId:fund.id,fundName:fund.name,value:change.value,weight,previousWeight:priorInstrumentTotal?(previousPositions.get(change.key)?.value||0)/priorInstrumentTotal:0,shares:change.shares,previousShares:change.previousShares,deltaShares:change.deltaShares,movement:change.movement,estimatedChange:change.estimatedChange,sourceUrl:now.sourceUrl,previousSourceUrl:old.sourceUrl});
 }}
 for(const row of rows.values()){if(mode==='value')row.weight=total?row.value/total:0;row.score=funds.length?Math.round(60*row.holders/funds.length+25*Math.max(0,row.buyers-row.sellers)/funds.length+15*Math.min(row.weight/.1,1)):0;}
 return [...rows.values()].sort((a,b)=>b.weight-a.weight||a.key.localeCompare(b.key));
}
export type Allocation={ticker:string;weight:number;amount:number;score:number};
export function allocate(rows:Aggregate[],budget:number,maxWeight:number,cashReserve:number,count:number):{positions:Allocation[];cash:number;cashWeight:number}{
 if(!Number.isFinite(budget)||budget<=0||!Number.isFinite(maxWeight)||maxWeight<=0||maxWeight>1||!Number.isFinite(cashReserve)||cashReserve<0||cashReserve>=1||!Number.isInteger(count)||count<1||count>50)throw Error('잘못된 포트폴리오 설정입니다.');
 const unique=new Map<string,Aggregate>();for(const row of [...rows].sort((a,b)=>b.score-a.score))if(row.kind==='EQUITY'&&row.ticker&&row.holders>0&&row.score>0&&!unique.has(row.ticker))unique.set(row.ticker,row);
 const picks=[...unique.values()].slice(0,count);const weights=picks.map(()=>0);let remaining=1-cashReserve;let active=picks.map((_,i)=>i);
 while(remaining>1e-10&&active.length){const sum=active.reduce((s,i)=>s+picks[i].score,0);let used=0;const next:number[]=[];
 for(const i of active){const add=Math.min(maxWeight-weights[i],remaining*picks[i].score/sum);weights[i]+=add;used+=add;if(weights[i]<maxWeight-1e-10)next.push(i);}remaining-=used;if(used<1e-10)break;active=next;}
 const positions=picks.map((r,i)=>({ticker:r.ticker!,weight:weights[i],amount:Math.floor(budget*weights[i]*100)/100,score:r.score}));const cash=budget-positions.reduce((s,p)=>s+p.amount,0);return {positions,cash,cashWeight:cash/budget};
}
export const movementLabel:Record<Movement,string>={new:'신규',increased:'확대',decreased:'축소',closed:'청산',unchanged:'유지'};
