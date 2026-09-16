"use client";

import {useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {aggregate,defaultCandidateFilter,researchCandidates,validateCandidateFilter,type Aggregate,type CandidateFilter,type Dataset} from '@/lib/domain';
import {filingCalendar,filingCalendarSource} from '@/lib/filing-calendar';
import {securityLabel,withSecurityMetadata} from '@/lib/security-metadata';
import strategyDefaults from '@/pipeline/strategy.json';
import {PipelineWorkspace} from '@/components/pipeline-workspace';
import {Switch} from '@/components/ui/switch';
import {Database,Layers3,RefreshCw,Settings2,ShieldCheck} from 'lucide-react';

const chartColors=['#adaee8','#8dafbd','#8f9cc5','#b2a4c8','#c4b28c','#c29ba9','#91b3a8','#798594'];
function Link({href,className,children}:{href:string;className?:string;children:ReactNode}){return <a href={href} className={className}>{children}</a>}
type WebContext={registerTool:(tool:{name:string;description:string;inputSchema:object;annotations:object;execute:(value:unknown)=>unknown},options:{signal:AbortSignal})=>unknown};
const percentage=(value:number)=>`${(value*100).toFixed(value>=.1?1:2)}%`;
function chartItems(rows:Aggregate[]){
 const holdings=rows.filter(row=>row.weight>0).sort((a,b)=>b.weight-a.weight);
 const top=holdings.slice(0,7).map(row=>({name:securityLabel(row),value:row.weight}));
 const rest=holdings.slice(7).reduce((sum,row)=>sum+row.weight,0);
 return rest?[...top,{name:`기타 ${holdings.length-7}종목`,value:rest}]:top;
}
function HoldingsDonut({items,center}:{items:{name:string;value:number}[];center:string}){
 const total=items.reduce((sum,item)=>sum+item.value,0);let cumulative=0;
 const stops=items.map((item,index)=>{const start=cumulative;cumulative+=total?item.value/total*100:0;return `${chartColors[index%chartColors.length]} ${start}% ${cumulative}%`});
 return <div className="holdings-donut-layout"><div className="holdings-donut" role="img" aria-label={`${center} 보유 비중: ${items.map(item=>`${item.name} ${percentage(total?item.value/total:0)}`).join(', ')}`} style={{background:total?`conic-gradient(${stops.join(',')})`:'#292a31'}}><div><b>{items.length}</b><span>구간</span></div></div><div className="holdings-legend">{items.map((item,index)=><div key={item.name}><span><i style={{background:chartColors[index%chartColors.length]}}/>{item.name}</span><b>{percentage(total?item.value/total:0)}</b></div>)}</div></div>;
}

export default function Dashboard({initialData}:{initialData:Dataset}){
 const initialReady=initialData.funds.filter(f=>f.status==='ready').map(f=>f.id);
 const recommended=(strategyDefaults.fundIds as string[]).filter(id=>initialReady.includes(id));
 const [data,setData]=useState(()=>withSecurityMetadata(initialData));
 const [selected,setSelected]=useState<string[]>(recommended.length?recommended:initialReady.slice(0,8));
 const [candidateFilter,setCandidateFilter]=useState<CandidateFilter>(defaultCandidateFilter);
 const [chartScope,setChartScope]=useState('combined');
 const [message,setMessage]=useState('');
 const ready=data.funds.filter(f=>f.status==='ready');
 const selectedReady=selected.filter(id=>ready.some(f=>f.id===id));
 const candidates=useMemo(()=>researchCandidates(aggregate(data,selectedReady,'equal'),undefined,candidateFilter),[data,selectedReady,candidateFilter]);
 const chartFundIds=chartScope==='combined'?selectedReady:selectedReady.includes(chartScope)?[chartScope]:selectedReady;
 const holdingsChart=chartItems(aggregate(data,chartFundIds,'equal'));
 const chartTitle=chartScope==='combined'?'선택 펀드 종합':ready.find(fund=>fund.id===chartScope)?.name||'선택 펀드 종합';
 const calendar=filingCalendar(data.period);
 const stateRef=useRef({selected:selectedReady,data});
 useEffect(()=>{stateRef.current={selected:selectedReady,data}},[selectedReady,data]);

 useEffect(()=>{const timer=window.setTimeout(()=>{try{
  const ids=JSON.parse(localStorage.getItem('hedge-fund-selection')||'null');
  if(Array.isArray(ids)){const valid=ids.filter(id=>typeof id==='string'&&initialData.funds.some(f=>f.id===id&&f.status!=='unavailable'));if(valid.length)setSelected(valid)}
  const stored=JSON.parse(localStorage.getItem('hedge-candidate-filter')||'null');if(stored)setCandidateFilter(validateCandidateFilter(stored));
 }catch{}},0);return()=>window.clearTimeout(timer)},[initialData]);

 useEffect(()=>{let cancelled=false;fetch('/api/filings').then(async response=>{if(!response.ok)throw Error();return await response.json() as Dataset}).then(next=>{if(!cancelled)setData(withSecurityMetadata(next))}).catch(()=>{if(!cancelled)setMessage('최신 데이터에 연결하지 못해 저장된 공시를 사용합니다.')});return()=>{cancelled=true}},[]);

 useEffect(()=>{const context=(document as unknown as {modelContext?:WebContext}).modelContext;if(!context?.registerTool)return;const lifecycle=new AbortController();
  const tools=[{name:'set_fund_selection',description:'Replace the selected funds used for the next analysis. This does not start research or trading.',inputSchema:{type:'object',properties:{fundIds:{type:'array',items:{type:'string'}}},required:['fundIds'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},execute:(input:unknown)=>{const ids=(input as {fundIds?:unknown})?.fundIds;if(!Array.isArray(ids)||!ids.every(id=>typeof id==='string'&&stateRef.current.data.funds.some(f=>f.id===id&&f.status==='ready')))throw Error('Unknown or unavailable fund');const distinct=[...new Set(ids)] as string[];changeSelection(distinct);return {selected:distinct};}},
  {name:'read_fund_consensus',description:'Read the selected funds and top common 13F equity holdings. No short-position inference.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute:()=>({selected:stateRef.current.selected,period:stateRef.current.data.period,holdings:aggregate(stateRef.current.data,stateRef.current.selected).filter(row=>row.holders>=2).slice(0,15).map(row=>({ticker:row.ticker,cusip:row.cusip,holders:row.holders,weight:row.weight}))})}];
  for(const tool of tools)try{Promise.resolve(context.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{})}catch{}return()=>lifecycle.abort();
 },[]);

 function changeSelection(ids:string[]){setSelected(ids);try{localStorage.setItem('hedge-fund-selection',JSON.stringify(ids))}catch{}}
 function changeFilter(next:CandidateFilter){setCandidateFilter(next);try{localStorage.setItem('hedge-candidate-filter',JSON.stringify(next))}catch{}}
 async function reload(){setMessage('공시 데이터를 확인하고 있습니다…');try{const response=await fetch('/api/filings',{cache:'no-store'});if(!response.ok)throw Error();setData(withSecurityMetadata(await response.json() as Dataset));setMessage('저장된 최신 공시를 불러왔습니다.')}catch{setMessage('공시를 불러오지 못했습니다. 현재 데이터를 유지합니다.')}}
 const recommendedReady=(strategyDefaults.fundIds as string[]).filter(id=>ready.some(f=>f.id===id));

 return <main className="workspace simple-shell">
  <header><Link className="brand" href="/"><Layers3/><span>HEDGE<span className="brand-light"> / INSIGHT</span></span></Link><div className="header-right"><span className="badge">터미널 승인 후에만 주문</span></div></header>
  <section className="simple-main">
   <div className="simple-hero"><div><p className="eyebrow">QUARTERLY RESEARCH · ACCOUNT PROPOSAL</p><h1>확인할 매매안을<br/>간단하게 만드세요.</h1><p>여러 펀드의 최근 보유 변화를 조사하고, 현재 토스 미국주식 계좌에 맞춘 주문안을 준비합니다.</p></div><div className="readiness-card"><span><Database/> {calendar.label} 공시</span><b>{data.period} 기준</b><small>{data.previousPeriod} 대비 · 비교 가능 펀드 {ready.length}개</small><button className="text-button" onClick={reload}><RefreshCw/> 공시 다시 확인</button></div></div>

   {message&&<div className="notice" role="status"><span>{message}</span><button className="text-button" onClick={()=>setMessage('')}>닫기</button></div>}
   {strategyDefaults.maxWeight===1&&<div className="simple-warning"><ShieldCheck/><div><b>현재 집중 제한이 완화되어 있습니다.</b><span>한 종목에 투자 가능 자본의 대부분이 배분될 수 있습니다. 주문 전에 수량과 금액을 확인하세요.</span></div></div>}

   <details className="simple-settings">
    <summary><span><Settings2/> 분석 설정</span><b>펀드 {selectedReady.length}개 · 2개 이상 같은 방향 · 후보 {candidates.length}개</b></summary>
    <div className="settings-body">
     <section><div className="settings-heading"><div><h2>펀드</h2><p>추천 조합으로 바로 시작하거나 필요한 경우에만 직접 바꾸세요.</p></div><div className="preset-actions"><button className="secondary-button" onClick={()=>changeSelection(recommendedReady)}>추천 {recommendedReady.length}개</button><button className="secondary-button" onClick={()=>changeSelection(ready.map(f=>f.id))}>전체</button></div></div>
      <details className="fund-picker"><summary>직접 선택 · 현재 {selectedReady.length}개</summary><div className="fund-picker-grid">{data.funds.map(fund=><label key={fund.id} data-disabled={fund.status!=='ready'}><span><b>{fund.name}</b><small>{fund.status==='ready'?fund.style:'데이터 준비 중'}</small></span><Switch checked={selected.includes(fund.id)} disabled={fund.status!=='ready'} onCheckedChange={on=>changeSelection(on?[...selected, fund.id]:selected.filter(id=>id!==fund.id))} aria-label={`${fund.name} 포함`}/></label>)}</div></details>
      <details className="holdings-chart"><summary>보유 비중 도넛 보기</summary><div className="holdings-chart-head"><div><b>{chartTitle}</b><span>{data.period} 기준 · 상위 7종목과 기타</span></div><select value={chartScope} onChange={event=>setChartScope(event.target.value)} aria-label="보유 비중을 확인할 펀드"><option value="combined">선택 펀드 종합</option>{selectedReady.map(id=>{const fund=ready.find(item=>item.id===id);return fund?<option key={id} value={id}>{fund.name}</option>:null})}</select></div>{selectedReady.length?<HoldingsDonut items={holdingsChart} center={chartTitle}/>:<p className="holdings-empty">먼저 비교할 펀드를 선택하세요.</p>}<p className="holdings-note">종합 비중은 선택한 펀드의 내부 보유 비중을 동일하게 평균합니다. 13F 공시 대상 주식·ETF 기준이며 전체 운용자산 비중과는 다를 수 있습니다.</p></details>
     </section>
     <section><h2>조사 대상</h2><p>기본값은 2개 이상 펀드가 같은 방향으로 움직인 종목입니다.</p><div className="direction-tabs" aria-label="후보 방향">{([['all','확대·축소 모두'],['increase','확대만'],['decrease','축소만']] as const).map(([value,label])=><button key={value} aria-pressed={candidateFilter.direction===value} onClick={()=>changeFilter({...candidateFilter,direction:value})}>{label}</button>)}</div><div className="advanced-settings"><label>같은 방향 최소 <select value={candidateFilter.minFunds} onChange={event=>changeFilter({...candidateFilter,minFunds:Number(event.target.value)})}>{Array.from({length:Math.max(1,Math.min(29,selectedReady.length-1))},(_,index)=>index+2).map(n=><option key={n} value={n}>{n}개 펀드</option>)}</select></label><label><input type="checkbox" checked={candidateFilter.includeMixed} onChange={event=>changeFilter({...candidateFilter,includeMixed:event.target.checked})}/> 확대·축소 의견이 함께 있는 종목 포함</label></div></section>
    </div>
   </details>

   <PipelineWorkspace fundIds={selectedReady} candidateFilter={candidateFilter}/>

   <details className="data-disclosure"><summary>데이터 기준과 한계</summary><div><p>13F는 분기 말 보유 스냅샷이며 실제 거래일, 분기 중 왕복매매나 공매도를 보여주지 않습니다. 분석 등급은 검증된 수익 확률이 아닙니다.</p><p>데이터 생성 {new Date(data.generatedAt).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})} · 출처 {data.source}</p><a href={filingCalendarSource} target="_blank" rel="noreferrer">SEC 공시 일정 확인 ↗</a></div></details>
   <footer><span>HEDGE / INSIGHT</span><span>리서치 도구 · 투자 판단과 주문 승인은 사용자 책임입니다.</span></footer>
  </section>
 </main>;
}
