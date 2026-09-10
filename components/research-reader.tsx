"use client";
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from '@/components/ui/sheet';

export type Research={jobId?:string;status?:string;error?:string;connectionWarning?:string;ticker?:string;decision?:{score:number;stance:string;thesis:string;risks:string[];evidenceUrls:string[];confidence:number;dataGaps?:string[]};reports?:Record<string,string>;sources?:string[];createdAt?:string;models?:Record<string,string>;progress?:{current:string;completed:number;total:number;percent:number;startedAt:string;updatedAt:string;steps:{id:string;label:string;status:string}[]}};
const titles:Record<string,string>={market_report:'시장·기술 분석',news_report:'뉴스 분석',fundamentals_report:'재무 분석',investment_plan:'강세·약세 검토와 투자 계획',trader_investment_plan:'매매안',final_trade_decision:'TradingAgents 리스크 검토·최종 의견'};
const stance:Record<string,string>={buy:'매수 검토',watch:'관찰',avoid:'회피'};
function safeUrl(url:string){try{return ['https:','http:'].includes(new URL(url).protocol)}catch{return false}}

export function ResearchProgress({result}:{result:Research}){
 const p=result.progress;
 if(result.status==='completed')return null;
 return <div className="research-progress" aria-live="polite"><b>{result.status==='failed'?'실행 실패':result.status==='queued'?'대기열에서 대기 중':p?.steps.find(s=>s.id===p.current)?.label||'리서치 실행 중'}</b>{p?<><p>{p.completed}/{p.total}단계 완료 · {p.percent}%</p><progress value={p.completed} max={p.total} aria-label="리서치 완료 단계"/><ol>{p.steps.map(s=><li key={s.id} data-status={s.status}>{s.status==='completed'?'✓':s.status==='running'?'진행 중':'대기'} · {s.label}</li>)}</ol><small>단계 완료 기준입니다. 소요 시간 비율이나 남은 시간 예측이 아닙니다. 마지막 단계 업데이트: {new Date(p.updatedAt).toLocaleTimeString('ko-KR')}</small></>:<p>서버의 단계 업데이트를 기다리고 있습니다.</p>}{result.connectionWarning&&<p role="status">{result.connectionWarning}</p>}</div>
}

export function ResearchReader({result,title,onClose}:{result?:Research;title:string;onClose:()=>void}){
 const decision=result?.decision;
 return <Sheet open={!!result} onOpenChange={open=>{if(!open)onClose()}}><SheetContent className="research-reader"><SheetHeader><SheetTitle>{title} · 리서치 보고서</SheetTitle><SheetDescription>요약과 분석 보고서 전문을 화면에서 확인합니다. AI 판단은 실제 주문이 아닙니다.</SheetDescription></SheetHeader>{result&&<div className="research-reader-body"><ResearchProgress result={result}/>{result.error&&<p role="alert">{result.error}</p>}{decision&&<section><h2>최종 종합 판단 · {stance[decision.stance]||decision.stance}</h2><p>점수 {decision.score}/100 · 모델 신뢰도 {(decision.confidence*100).toFixed(0)}% (검증된 확률 아님)</p><div className="report-text">{decision.thesis}</div><h3>위험 요인</h3><ul>{decision.risks.map((r,i)=><li key={i}>{r}</li>)}</ul><h3>확인하지 못한 근거</h3>{decision.dataGaps?.length?<ul>{decision.dataGaps.map((g,i)=><li key={i}>{g}</li>)}</ul>:<p>{decision.dataGaps?'모델이 명시한 누락 항목 없음':'이 보고서에 누락 근거 항목이 없습니다.'}</p>}</section>}<section><h2>분석 보고서 전문</h2>{Object.entries(result.reports||{}).map(([key,report])=><details key={key} className="report-section" open={key==='market_report'}><summary>{titles[key]||key}</summary><div className="report-text">{report}</div></details>)}</section><section><h2>출처</h2><ul>{[...new Set([...(decision?.evidenceUrls||[]),...(result.sources||[])])].filter(safeUrl).map(url=><li key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a></li>)}</ul></section><p className="muted">{result.createdAt&&`작성: ${new Date(result.createdAt).toLocaleString('ko-KR')}`}<br/>{result.models&&`모델: ${Object.values(result.models).join(' · ')}`}</p></div>}</SheetContent></Sheet>
}
