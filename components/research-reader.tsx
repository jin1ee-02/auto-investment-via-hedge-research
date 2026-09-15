"use client";
import React,{Fragment,type ReactNode} from 'react';
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from '@/components/ui/sheet';
import {Tabs,TabsContent,TabsList,TabsTrigger} from '@/components/ui/tabs';

type Decision={rating?:string;score:number;stance:string;thesis:string;risks:string[];evidenceUrls:string[];confidence?:number;dataGaps?:string[]};
type Progress={current:string;completed:number;total:number;percent:number;startedAt:string;updatedAt:string;steps:{id:string;label:string;status:string}[]};
export type Research={jobId?:string;status?:string;period?:string;error?:string;connectionWarning?:string;ticker?:string;decision?:Decision;blockingDataGaps?:string[];reports?:Record<string,string>;sources?:string[];createdAt?:string;models?:Record<string,string>;progress?:Progress;upstreamSignal?:string;engine?:string;fundIds?:string[];brokerConnected?:boolean;cacheHit?:boolean};

const reportMeta:Record<string,{title:string;role:string}>={
 market_report:{title:'시장·기술 분석',role:'시장 분석가'},
 sentiment_report:{title:'감성 분석',role:'감성 분석가'},
 news_report:{title:'뉴스·거시 분석',role:'뉴스 분석가'},
 fundamentals_report:{title:'재무·가치 분석',role:'재무 분석가'},
 investment_plan:{title:'강세·약세 종합 계획',role:'리서치 책임자'},
 trader_investment_plan:{title:'매매 관점 제안',role:'Trader'},
 final_trade_decision:{title:'TradingAgents 최종 의견',role:'포트폴리오 책임자'},
};
const reportGroups=[
 {title:'시장과 기업 근거',description:'가격 흐름, 여론, 최신 사건과 재무 상태를 서로 독립적으로 확인합니다.',keys:['market_report','sentiment_report','news_report','fundamentals_report']},
 {title:'의사결정 교차검토',description:'강세·약세 논쟁을 종합한 뒤 매매 관점과 위험 조정 결론을 확인합니다.',keys:['investment_plan','trader_investment_plan','final_trade_decision']},
];
const stance:Record<string,string>={buy:'매수 검토',watch:'관찰',avoid:'회피'};

function safeUrl(url:string){try{return ['https:','http:'].includes(new URL(url).protocol)}catch{return false}}
function host(url:string){try{return new URL(url).hostname.replace(/^www\./,'')}catch{return '출처'}}
function signalBucket(signal?:string){
 const value=(signal||'').toUpperCase();
 if(value.includes('UNDERWEIGHT')||value.includes('SELL'))return 'avoid';
 if(value.includes('OVERWEIGHT')||value.includes('BUY'))return 'buy';
 if(value.includes('HOLD'))return 'watch';
 return '';
}
function signalLabel(signal?:string){
 const bucket=signalBucket(signal);
 return bucket?({buy:'매수·비중 확대',watch:'보유',avoid:'매도·비중 축소'}[bucket]):'확인되지 않음';
}
function formatDate(value?:string){if(!value)return '확인되지 않음';const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString('ko-KR')}

function inlineMarkdown(text:string,keyBase:string):ReactNode[]{
 const nodes:ReactNode[]=[];
 const token=/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g;
 let cursor=0,index=0,match:RegExpExecArray|null;
 while((match=token.exec(text))){
  if(match.index>cursor)nodes.push(text.slice(cursor,match.index));
  const value=match[0],key=`${keyBase}-${index++}`;
  if(value.startsWith('**'))nodes.push(<strong key={key}>{value.slice(2,-2)}</strong>);
  else if(value.startsWith('`'))nodes.push(<code key={key}>{value.slice(1,-1)}</code>);
  else{
   const link=value.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
   nodes.push(link&&safeUrl(link[2])?<a key={key} href={link[2]} target="_blank" rel="noreferrer">{link[1]} ↗</a>:value);
  }
  cursor=match.index+value.length;
 }
 if(cursor<text.length)nodes.push(text.slice(cursor));
 return nodes;
}

function tableCells(line:string){return line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(cell=>cell.trim())}
function isTableDivider(line:string){return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)}
function isBlockStart(line:string,next?:string){return /^#{1,4}\s+/.test(line)||/^```/.test(line)||/^\s*([-*]|\d+\.)\s+/.test(line)||/^>\s?/.test(line)||/^\s*(---|\*\*\*)\s*$/.test(line)||(!!next&&line.includes('|')&&isTableDivider(next))}

export function MarkdownReport({source}:{source:string}){
 const lines=source.replace(/\r\n/g,'\n').split('\n'),blocks:ReactNode[]=[];
 let i=0,block=0;
 while(i<lines.length){
  const line=lines[i];
  if(!line.trim()){i++;continue}
  if(/^```/.test(line)){
   const language=line.replace(/^```/,'').trim();i++;
   const code:string[]=[];while(i<lines.length&&!/^```/.test(lines[i]))code.push(lines[i++]);
   if(i<lines.length)i++;
   blocks.push(<pre key={block++} data-language={language||undefined}><code>{code.join('\n')}</code></pre>);continue;
  }
  const heading=line.match(/^(#{1,4})\s+(.+)$/);
  if(heading){blocks.push(React.createElement(`h${heading[1].length}`,{key:block++},inlineMarkdown(heading[2],`h-${block}`)));i++;continue}
  if(/^\s*(---|\*\*\*)\s*$/.test(line)){blocks.push(<hr key={block++}/>);i++;continue}
  if(i+1<lines.length&&line.includes('|')&&isTableDivider(lines[i+1])){
   const headers=tableCells(line);i+=2;const rows:string[][]=[];
   while(i<lines.length&&lines[i].includes('|')&&lines[i].trim())rows.push(tableCells(lines[i++]));
   blocks.push(<div className="markdown-table-scroll" key={block++}><table><thead><tr>{headers.map((cell,n)=><th key={n}>{inlineMarkdown(cell,`th-${block}-${n}`)}</th>)}</tr></thead><tbody>{rows.map((row,r)=><tr key={r}>{row.map((cell,c)=><td key={c}>{inlineMarkdown(cell,`td-${block}-${r}-${c}`)}</td>)}</tr>)}</tbody></table></div>);continue;
  }
  const list=line.match(/^\s*([-*]|\d+\.)\s+(.+)$/);
  if(list){
   const ordered=/\d+\./.test(list[1]),items:string[]=[];
   while(i<lines.length){const item=lines[i].match(/^\s*([-*]|\d+\.)\s+(.+)$/);if(!item||(/\d+\./.test(item[1])!==ordered))break;items.push(item[2]);i++}
   const children=items.map((item,n)=><li key={n}>{inlineMarkdown(item,`li-${block}-${n}`)}</li>);
   blocks.push(ordered?<ol key={block++}>{children}</ol>:<ul key={block++}>{children}</ul>);continue;
  }
  if(/^>\s?/.test(line)){
   const quote:string[]=[];while(i<lines.length&&/^>\s?/.test(lines[i]))quote.push(lines[i++].replace(/^>\s?/,''));
   blocks.push(<blockquote key={block++}>{quote.map((part,n)=><Fragment key={n}>{n>0&&<br/>}{inlineMarkdown(part,`q-${block}-${n}`)}</Fragment>)}</blockquote>);continue;
  }
  const paragraph:string[]=[line];i++;
  while(i<lines.length&&lines[i].trim()&&!isBlockStart(lines[i],lines[i+1]))paragraph.push(lines[i++]);
  blocks.push(<p key={block++}>{paragraph.map((part,n)=><Fragment key={n}>{n>0&&<br/>}{inlineMarkdown(part,`p-${block}-${n}`)}</Fragment>)}</p>);
 }
 return <div className="markdown-report">{blocks}</div>;
}

function downloadResearch(result:Research){
 const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
 const anchor=document.createElement('a');anchor.href=url;anchor.download=`${result.ticker||'research'}-research.json`;anchor.click();URL.revokeObjectURL(url);
}

export function ResearchConclusion({result,period}:{result?:Research;period:string}){
 const d=result?.decision;
 if(!d)return null;
 return <section className="research-conclusion" data-stance={d.stance} aria-label="TradingAgents 최종 결론"><div className="section-heading"><strong>TradingAgents · {signalLabel(result?.upstreamSignal)}</strong><span>{d.score}/100</span></div><p className="report-text">{d.thesis}</p>{!!d.dataGaps?.length&&<p className="negative">치명적 데이터 문제 {d.dataGaps.length}개 · {d.dataGaps[0]}</p>}<small>작성 {formatDate(result?.createdAt)} · 점수는 최종 등급의 결정론적 강도</small>{result?.period!==period&&<p className="negative">현재 공시와 보고서 기준이 다르거나 확인되지 않습니다. 다시 조사하세요.</p>}<small>축소 의견은 공매도 지시가 아닙니다.</small></section>
}

export function ResearchProgress({result}:{result:Research}){
 const p=result.progress;
 if(result.status==='completed')return null;
 return <div className="research-progress" aria-live="polite"><b>{result.status==='failed'?'실행 실패':result.status==='queued'?'대기열에서 대기 중':p?.steps.find(s=>s.id===p.current)?.label||'리서치 실행 중'}</b>{p?<><p>{p.completed}/{p.total}단계 완료 · {p.percent}%</p><progress value={p.completed} max={p.total} aria-label="리서치 완료 단계"/><ol>{p.steps.map(s=><li key={s.id} data-status={s.status}>{s.status==='completed'?'✓':s.status==='running'?'진행 중':'대기'} · {s.label}</li>)}</ol><small>단계 완료 기준입니다. 소요 시간 비율이나 남은 시간 예측이 아닙니다. 마지막 단계 업데이트: {new Date(p.updatedAt).toLocaleTimeString('ko-KR')}</small></>:<p>서버의 단계 업데이트를 기다리고 있습니다.</p>}{result.connectionWarning&&<p role="status">{result.connectionWarning}</p>}</div>
}

export function ResearchReader({result,title,onClose}:{result?:Research;title:string;onClose:()=>void}){
 const decision=result?.decision,reports=result?.reports||{};
 const sources=result?[...new Set([...(decision?.evidenceUrls||[]),...(result.sources||[])])].filter(safeUrl):[];
 const reportCount=Object.values(reports).filter(Boolean).length;
 const critical=new Set(result?.blockingDataGaps||[]);
 return <Sheet open={!!result} onOpenChange={open=>{if(!open)onClose()}}><SheetContent className="research-reader"><SheetHeader><SheetTitle>{title} · 투자 리서치</SheetTitle><SheetDescription>13F는 조사 배경으로만 제공되며, 매매 방향은 TradingAgents Portfolio Manager의 최종 등급 하나로 결정합니다.</SheetDescription></SheetHeader>{result&&<div className="research-reader-body"><ResearchProgress result={result}/>{result.error&&<p role="alert" className="report-error">{result.error}</p>}{decision&&<section className="decision-brief" data-stance={decision.stance}><div className="decision-heading"><div><p className="eyebrow">TRADINGAGENTS FINAL DECISION</p><h2>{signalLabel(result.upstreamSignal)}</h2></div><div className="decision-rating"><span>{stance[decision.stance]||decision.stance}</span><strong>{decision.score}<small>/100</small></strong></div></div><p className="decision-thesis">{decision.thesis}</p><div className="decision-metrics"><div><span>최종 등급</span><strong>{result.upstreamSignal||'확인되지 않음'}</strong><small>유일한 AI 매매 판단</small></div><div><span>13F 기준</span><strong>{result.period||'미확인'}</strong><small>후보 선정·맥락 데이터</small></div><div><span>검증 가능한 근거</span><strong>{sources.length}개</strong><small>보고서에 연결된 URL</small></div></div><div className="decision-columns"><div><h3>핵심 위험</h3>{decision.risks.length?<ul>{decision.risks.map((risk,i)=><li key={i}>{risk}</li>)}</ul>:<p className="muted">최종 보고서 전문에서 위험 근거를 확인하세요.</p>}</div><div><h3>확인하지 못한 근거</h3>{decision.dataGaps?.length?<><p className={critical.size?'negative':'muted'}>{critical.size?`주문 차단 ${critical.size}개 · 일반 한계 ${decision.dataGaps.length-critical.size}개`:`일반 리서치 한계 ${decision.dataGaps.length}개 · 주문을 차단하지 않음`}</p><ul>{decision.dataGaps.map((gap,i)=><li className={critical.has(gap)?'negative':undefined} key={i}>{critical.has(gap)?'치명적 · ':''}{gap}</li>)}</ul></>:<p className="evidence-clear">추가로 명시된 누락 근거가 없습니다.</p>}</div></div></section>}<Tabs defaultValue="reports" className="research-tabs"><div className="report-toolbar"><TabsList variant="line" aria-label="리서치 보고서 보기"><TabsTrigger value="reports">분석 보고서 {reportCount}</TabsTrigger><TabsTrigger value="sources">출처 {sources.length}</TabsTrigger><TabsTrigger value="run">실행 정보</TabsTrigger></TabsList><button className="secondary-button" onClick={()=>downloadResearch(result)}>JSON 저장</button></div><TabsContent value="reports">{reportGroups.map(group=>{const available=group.keys.filter(key=>reports[key]);if(!available.length)return null;return <section className="report-group" key={group.title}><div className="report-group-heading"><h2>{group.title}</h2><p>{group.description}</p></div>{available.map(key=>{const meta=reportMeta[key]||{title:key,role:'분석 에이전트'};return <details key={key} className="report-section" open={key==='final_trade_decision'}><summary><span><small>{meta.role}</small>{meta.title}</span><b>열기</b></summary><MarkdownReport source={reports[key]}/></details>})}</section>})}</TabsContent><TabsContent value="sources"><section className="source-panel"><div className="report-group-heading"><h2>검증 가능한 출처</h2><p>TradingAgents 보고서와 13F 후보 데이터에서 확인된 링크입니다. 같은 주소는 한 번만 표시합니다.</p></div>{sources.length?<ol className="source-list">{sources.map((url,i)=><li key={url}><span>{String(i+1).padStart(2,'0')}</span><a href={url} target="_blank" rel="noreferrer"><strong>{host(url)}</strong><small>{url}</small></a></li>)}</ol>:<p className="empty-report">저장된 출처가 없습니다. 이 상태에서는 자동 배분에 사용하지 마세요.</p>}</section></TabsContent><TabsContent value="run"><section className="run-panel"><div className="report-group-heading"><h2>보고서 기준과 실행 정보</h2><p>결론을 다시 사용할 때 동일한 공시·모델·작성 시점인지 확인하세요.</p></div><dl><div><dt>작성 시각</dt><dd>{formatDate(result.createdAt)}</dd></div><div><dt>13F 기준 분기</dt><dd>{result.period||'확인되지 않음'}</dd></div><div><dt>분석 엔진</dt><dd>{result.engine||'TradingAgents'}</dd></div><div><dt>선택 펀드</dt><dd>{result.fundIds?.length?`${result.fundIds.length}개`:'저장 정보 없음'}</dd></div><div><dt>모델</dt><dd>{result.models?Object.values(result.models).filter(Boolean).join(' · '):'확인되지 않음'}</dd></div><div><dt>주문 연결</dt><dd>{result.brokerConnected?'연결됨':'이 보고서에서는 비활성'}</dd></div></dl><div className="notice">점수는 TradingAgents의 5단계 등급을 배분용 강도로 변환한 값입니다. 최신 가격·공시·뉴스가 달라졌다면 보고서를 다시 생성해야 합니다.</div></section></TabsContent></Tabs></div>}</SheetContent></Sheet>
}
