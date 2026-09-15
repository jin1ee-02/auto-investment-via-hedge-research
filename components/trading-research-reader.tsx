"use client";
import {Sheet,SheetContent,SheetDescription,SheetHeader,SheetTitle} from './ui/sheet';
import {MarkdownReport,type Research} from './research-reader';

const labels:Record<string,string>={market_report:'시장·기술 분석',sentiment_report:'감성 분석',news_report:'뉴스·거시 분석',fundamentals_report:'재무·가치 분석',investment_plan:'강세·약세 종합 계획',trader_investment_plan:'Trader 제안',final_trade_decision:'TradingAgents 최종 판단'};
const ratingLabel:Record<string,string>={Buy:'매수',Overweight:'비중 확대',Hold:'유지',Underweight:'비중 축소',Sell:'매도'};

export function TradingResearchReader({result,title,onClose}:{result?:Research;title:string;onClose:()=>void}){
 const decision=result?.decision,reports=result?.reports||{},critical=new Set(result?.blockingDataGaps||[]);
 const rating=result?.upstreamSignal||decision?.rating||'확인되지 않음';
 const sources=[...new Set([...(decision?.evidenceUrls||[]),...(result?.sources||[])])];
 function download(){if(!result)return;const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`${result.ticker||'research'}-research.json`;a.click();URL.revokeObjectURL(url)}
 return <Sheet open={!!result} onOpenChange={open=>{if(!open)onClose()}}><SheetContent className="research-reader"><SheetHeader><SheetTitle>{title} · TradingAgents 리서치</SheetTitle><SheetDescription>추가 AI 재판단 없이 TradingAgents의 최종 등급을 그대로 사용합니다.</SheetDescription></SheetHeader>{result&&<div className="research-reader-body">
  <section className="decision-brief" data-stance={decision?.stance}><div className="decision-heading"><div><p className="eyebrow">TRADINGAGENTS FINAL DECISION</p><h2>{ratingLabel[rating]||rating}</h2></div><div className="decision-rating"><span>신호 강도</span><strong>{decision?.score??0}<small>/100</small></strong></div></div><p className="decision-thesis">{decision?.thesis||reports.final_trade_decision}</p><div className="decision-metrics"><div><span>최종 등급</span><strong>{rating}</strong><small>유일한 AI 매매 판단</small></div><div><span>13F 기준</span><strong>{result.period||'미확인'}</strong><small>후보 선정 데이터</small></div><div><span>출처</span><strong>{sources.length}개</strong><small>보고서 연결 URL</small></div></div>{decision?.dataGaps?.length?<div className="decision-columns"><div><h3>주문 차단 데이터 문제</h3>{critical.size?<ul>{[...critical].map((gap,i)=><li className="negative" key={i}>{gap}</li>)}</ul>:<p className="evidence-clear">치명적인 데이터 무결성 문제 없음</p>}</div><div><h3>일반 리서치 한계</h3><ul>{decision.dataGaps.filter(gap=>!critical.has(gap)).map((gap,i)=><li key={i}>{gap}</li>)}</ul></div></div>:null}</section>
  <div className="report-toolbar"><strong>TradingAgents 전체 보고서</strong><button className="secondary-button" onClick={download}>JSON 저장</button></div>
  {Object.entries(reports).map(([key,report])=><details key={key} className="report-section" open={key==='final_trade_decision'}><summary><span><small>TradingAgents</small>{labels[key]||key}</span><b>열기</b></summary><MarkdownReport source={report}/></details>)}
  <section className="source-panel"><div className="report-group-heading"><h2>출처</h2><p>보고서와 13F 후보 데이터에 연결된 주소입니다.</p></div>{sources.length?<ol className="source-list">{sources.map((url,i)=><li key={url}><span>{String(i+1).padStart(2,'0')}</span><a href={url} target="_blank" rel="noreferrer"><small>{url}</small></a></li>)}</ol>:<p className="empty-report">저장된 출처가 없습니다.</p>}</section>
 </div>}</SheetContent></Sheet>
}
