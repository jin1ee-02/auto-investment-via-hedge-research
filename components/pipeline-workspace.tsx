"use client";

import {useEffect,useState} from 'react';
import {Check,ChevronDown,LoaderCircle,ShieldCheck} from 'lucide-react';
import type {CandidateFilter} from '@/lib/domain';
import {ApprovalCenter,type Review} from './approval-center';
import type {Research as FullResearch} from './research-reader';
import {TradingResearchReader} from './trading-research-reader';

type Candidate={key:string;ticker:string;buyers:number;sellers:number;holders:number};
type Research=FullResearch&{ticker:string;action?:string;actionReason?:string;allocationScore?:number};
export type PipelineResult={runId:string;status:string;stage?:string;proposalStatus?:string;error?:string;candidateCount?:number;selectedCandidates:Candidate[];research?:Research[];currentCandidate?:{index:number;total:number;ticker:string;status?:string;progress?:{percent:number;current:string}};plan?:{period:string;accountSnapshot:{asOf:string;usdCashBuyingPower:string;usHoldingsValue:string;usCapitalUsd:string;protectedHoldingsValue:string;usHoldingCount:number;excludedKrHoldingCount:number;excludedAssets:{symbol?:string;marketCountry?:string;currency?:string;marketValue:string}[]};portfolio:{positions:{ticker:string;amount:number;weight:number;allocationScore:number}[];cashTarget:string;protectedHoldingsValue:string};research:Research[];excluded:{ticker:string;reason:string}[];orders:{symbol:string;side:string;quantity:string;price:string;rationale?:string}[];proposalMessage?:string};review?:Review|null};

const money=(value:string|number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(Number(value));
const pipelineStorageKey='hedge-active-pipeline-run-id';
const candidateCountStorageKey='hedge-pipeline-candidate-count';

function friendlyError(result:PipelineResult){
 if(result.stage==='research')return {title:'종목 조사를 완료하지 못했습니다.',body:result.error||'완료된 분석은 저장했습니다. 연결 상태를 확인한 뒤 다시 시도하세요.'};
 if(result.stage==='account')return {title:'계좌 기준 매매안을 만들지 못했습니다.',body:result.error||'토스 계좌 연결과 현재 주문 상태를 확인하세요.'};
 return {title:'매매안 생성을 완료하지 못했습니다.',body:result.error||'잠시 후 다시 시도하세요.'};
}

export function PipelineWorkspace({fundIds,candidateFilter}:{fundIds:string[];candidateFilter:CandidateFilter}){
 const [runId,setRunId]=useState('');
 const [result,setResult]=useState<PipelineResult|null>(null);
 const [error,setError]=useState('');
 const [readerTicker,setReaderTicker]=useState<string|null>(null);
 const [candidateCount,setCandidateCount]=useState(6);
 const running=result?.status==='queued'||result?.status==='running';

 useEffect(()=>{const timer=window.setTimeout(()=>{try{const saved=Number(localStorage.getItem(candidateCountStorageKey));if(Number.isInteger(saved)&&saved>=1&&saved<=8)setCandidateCount(saved)}catch{}},0);return()=>window.clearTimeout(timer)},[]);
 useEffect(()=>{let stopped=false;const restore=async()=>{try{const saved=localStorage.getItem(pipelineStorageKey);if(saved&&/^[a-f0-9]{32}$/.test(saved)){if(!stopped)setRunId(saved);return}}catch{}try{const response=await fetch('/api/pipeline?active=1',{cache:'no-store'});if(!response.ok)return;const next=await response.json() as PipelineResult;if(stopped)return;setResult(next);setRunId(next.runId);try{localStorage.setItem(pipelineStorageKey,next.runId)}catch{}}catch{}};void restore();return()=>{stopped=true}},[]);
 useEffect(()=>{if(!runId)return;let stopped=false;const poll=async()=>{try{const response=await fetch(`/api/pipeline?runId=${runId}`,{cache:'no-store'});const next=await response.json() as PipelineResult;if(!response.ok)throw Error(next.error||'상태 확인 실패');if(stopped)return;setError('');setResult(next);if(!['queued','running'].includes(next.status))return;timer=window.setTimeout(poll,2000)}catch(e){if(!stopped)setError(e instanceof Error?e.message:'상태 확인 실패')}};let timer=window.setTimeout(poll,100);return()=>{stopped=true;window.clearTimeout(timer)}},[runId]);

 async function start(){setError('');setResult(null);try{const response=await fetch('/api/pipeline',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fundIds,candidateFilter,candidateCount})});const next=await response.json() as PipelineResult;if(!response.ok)throw Error(next.error||'파이프라인 시작 실패');setResult(next);setRunId(next.runId);try{localStorage.setItem(pipelineStorageKey,next.runId);localStorage.setItem(candidateCountStorageKey,String(candidateCount))}catch{}}catch(e){setError(e instanceof Error?e.message:'매매안 생성을 시작하지 못했습니다.')}}

 const plan=result?.plan;
 const readerResult=readerTicker?result?.research?.find(report=>report.ticker===readerTicker):undefined;
 const completed=result?.research?.length||0;
 const total=result?.selectedCandidates?.length||candidateCount;
 const progress=running?Math.max(result?.currentCandidate?.progress?.percent||0,completed===total?100:Math.round(100*(completed+(result?.currentCandidate?0.35:0))/Math.max(1,total))):100;
 const buys=plan?.research.filter(item=>item.action==='buy')||[];
 const sells=plan?.research.filter(item=>item.action==='sell')||[];
 const holds=plan?.research.filter(item=>item.action!=='buy'&&item.action!=='sell')||[];
 const buyTotal=plan?.orders.filter(order=>order.side==='BUY').reduce((sum,order)=>sum+Number(order.quantity)*Number(order.price),0)||0;
 const sellTotal=plan?.orders.filter(order=>order.side==='SELL').reduce((sum,order)=>sum+Number(order.quantity)*Number(order.price),0)||0;
 const failure=result?.status==='failed'?friendlyError(result):null;

 return <div className="pipeline-workspace simple-pipeline">
  <TradingResearchReader result={readerResult} title={readerTicker||''} onClose={()=>setReaderTicker(null)}/>

  <section className="panel simple-launch">
   <div><p className="eyebrow">NEW PROPOSAL</p><h2>새 매매안 만들기</h2><p>추천 설정으로 상위 {candidateCount}개 종목을 조사한 뒤 현재 토스 계좌에 맞춘 주문안을 준비합니다.</p><span className="launch-meta">펀드 {fundIds.length}개 · 같은 방향 {candidateFilter.minFunds}개 이상 · 주문 자동 전송 없음</span></div>
   <div className="launch-actions"><details><summary>분석 범위 <ChevronDown/></summary><label><input type="radio" name="scope" checked={candidateCount===3} onChange={()=>setCandidateCount(3)}/> 빠르게 · 3개</label><label><input type="radio" name="scope" checked={candidateCount===6} onChange={()=>setCandidateCount(6)}/> 기본 · 6개</label><label><input type="radio" name="scope" checked={candidateCount===8} onChange={()=>setCandidateCount(8)}/> 넓게 · 8개</label></details><button className="primary-button create-proposal" disabled={!fundIds.length||running} onClick={start}>{running?<><LoaderCircle className="spin"/>만드는 중</>:result?.status==='completed'?'최신 계좌로 다시 만들기':'매매안 만들기'}</button></div>
  </section>

  {error&&<div className="simple-error" role="alert"><b>상태를 확인할 수 없습니다.</b><span>{error}</span></div>}

  {running&&<section className="panel simple-progress" aria-live="polite"><div className="progress-heading"><div><p className="eyebrow">IN PROGRESS</p><h2>매매안을 만들고 있습니다.</h2></div><strong>{completed} / {total}</strong></div><div className="progress-track"><i style={{width:`${progress}%`}}/></div><p>{result?.currentCandidate?<><b>{result.currentCandidate.ticker}</b> 조사 중 · {result.currentCandidate.progress?.current||'분석 준비 중'}</>:'조사할 종목을 준비하고 있습니다.'}</p><details className="progress-details"><summary>진행 상황 자세히</summary><div>{result?.selectedCandidates.map((candidate,index)=>{const report=result.research?.find(item=>item.ticker===candidate.ticker);const active=result.currentCandidate?.ticker===candidate.ticker;return <span key={candidate.key} data-state={report?'done':active?'active':'pending'}>{report?<Check/>:<i>{index+1}</i>}<b>{candidate.ticker}</b><small>{report?.cacheHit?'완료한 최신 분석 사용':active?'조사 중':'대기'}</small></span>})}</div></details></section>}

  {failure&&<section className="panel simple-failure"><b>{failure.title}</b><p>{failure.body}</p><button className="secondary-button" onClick={start}>다시 시도</button></section>}

  {plan&&result?.status==='completed'&&<>
   <section className="panel result-overview"><div><p className="eyebrow">LATEST RESULT</p><h2>{plan.orders.length?'매매안이 준비되었습니다.':'이번에는 실행할 주문이 없습니다.'}</h2><p>{plan.orders.length?'주문 전 수량과 금액을 확인하세요. 아직 어떤 주문도 전송되지 않았습니다.':'조사는 정상적으로 끝났으며 현재 보유를 그대로 유지합니다.'}</p></div><div className="result-counts"><span className="positive"><b>{buys.length}</b>매수 검토</span><span className="negative"><b>{sells.length}</b>매도 검토</span><span><b>{holds.length}</b>유지</span></div></section>

   <section className="account-glance"><span><small>현재 미국 투자 가능 자본</small><b>{money(plan.accountSnapshot.usCapitalUsd)}</b></span><span><small>USD 매수가능 현금</small><b>{money(plan.accountSnapshot.usdCashBuyingPower)}</b></span><span><small>계좌 확인 시각</small><b>{new Date(plan.accountSnapshot.asOf).toLocaleString('ko-KR')}</b></span></section>

   {plan.orders.length>0?<section className="panel simple-orders"><div className="section-heading"><div><p className="eyebrow">PROPOSED ORDERS</p><h2>검토할 주문 {plan.orders.length}건</h2></div><div className="order-totals"><span>예상 매수 <b>{money(buyTotal)}</b></span><span>예상 매도 <b>{money(sellTotal)}</b></span></div></div><div className="order-list">{plan.orders.map(order=><article key={`${order.symbol}-${order.side}`} data-side={order.side}><div><b>{order.symbol}</b><span>{order.side==='BUY'?'매수':'매도'}</span></div><strong>{Number(order.quantity).toLocaleString()}주</strong><p>{money(order.price)} 지정가 · 예상 {money(Number(order.quantity)*Number(order.price))}</p><small>{order.rationale}</small></article>)}</div></section>:<section className="panel no-orders"><ShieldCheck/><div><h2>현재 계좌를 변경하지 않습니다.</h2><p>13F 방향과 현재 분석이 일치하는 주문이 없거나, 안전 조건에 따라 주문안이 보류되었습니다.</p>{plan.proposalMessage&&<p className="negative">{plan.proposalMessage}</p>}</div></section>}

   <section className="panel decision-list"><div className="section-heading"><h2>판단 근거</h2><span>{plan.period} 공시 기준</span></div>{[...buys,...sells].map(item=><article key={item.ticker} data-action={item.action}><div><b>{item.ticker}</b><span>{item.action==='buy'?'매수 검토':'매도 검토'}</span></div><p>{item.decision?.thesis}</p><small>{item.actionReason}</small><button className="text-button" onClick={()=>setReaderTicker(item.ticker)}>전체 분석 읽기</button></article>)}{holds.length>0&&<details className="hold-list"><summary>유지 {holds.length}종목과 이유</summary>{holds.map(item=><article key={item.ticker}><div><b>{item.ticker}</b><span>유지</span></div><p>{item.actionReason}</p><button className="text-button" onClick={()=>setReaderTicker(item.ticker)}>전체 분석 읽기</button></article>)}</details>}</section>

   <details className="account-details"><summary>계좌와 배분 기준 자세히</summary><div><p>미국주식 평가액 {money(plan.accountSnapshot.usHoldingsValue)} · 이번 매매안에서 유지하는 보유액 {money(plan.accountSnapshot.protectedHoldingsValue)} · 목표 현금 {money(plan.portfolio.cashTarget)}</p><p>국내주식과 원화 등 제외 자산 {plan.accountSnapshot.excludedAssets.length}건은 자본 계산과 주문 대상에 포함하지 않았습니다.</p></div></details>

   {result.review&&<ApprovalCenter review={result.review}/>}
  </>}
 </div>;
}
