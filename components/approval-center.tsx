"use client";

import {useEffect,useState} from 'react';
import {Check,Clipboard,Download,LockKeyhole} from 'lucide-react';

export type Review={schemaVersion:1;id:string;status:string;account:string;expiresAt:string;createdAt:string;orders:{symbol:string;side:string;quantity:string;price:string;rationale?:string}[];plan:{period:string;research:{ticker:string;action?:string;actionReason?:string;allocationScore?:number;decision:{stance:string;thesis?:string;risks?:string[];dataGaps?:string[]}}[]}};

function save(name:string,content:string,type:string){const url=URL.createObjectURL(new Blob([content],{type}));const anchor=document.createElement('a');anchor.href=url;anchor.download=name;anchor.click();URL.revokeObjectURL(url)}
const escapeHtml=(value:unknown)=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]||char));
function exportHtml(review:Review){const orders=review.orders.map(order=>`<tr><td>${escapeHtml(order.symbol)}</td><td>${escapeHtml(order.side)}</td><td>${escapeHtml(order.quantity)}</td><td>${escapeHtml(order.price)}</td><td>${escapeHtml(order.rationale)}</td></tr>`).join('');const research=review.plan.research.map(item=>`<h2>${escapeHtml(item.ticker)} · ${escapeHtml(item.action)}</h2><p>${escapeHtml(item.actionReason)}</p><p>${escapeHtml(item.decision.thesis)}</p>`).join('');return `<!doctype html><html lang="ko"><meta charset="utf-8"><title>Hedge Insight ${escapeHtml(review.id)}</title><style>body{max-width:960px;margin:40px auto;font:16px/1.6 system-ui}table{width:100%;border-collapse:collapse}td,th{padding:8px;border:1px solid #ccc;text-align:left}</style><h1>${escapeHtml(review.plan.period)} 주문 검토</h1><p>계좌 ${escapeHtml(review.account)} · 만료 ${escapeHtml(review.expiresAt)}</p><table><thead><tr><th>종목</th><th>방향</th><th>수량</th><th>가격</th><th>근거</th></tr></thead><tbody>${orders}</tbody></table>${research}</html>`}

export function ApprovalCenter({review}:{review?:Review|null}={}){
 const [now,setNow]=useState<number|null>(null);
 const [copied,setCopied]=useState(false);
 useEffect(()=>{const initial=window.setTimeout(()=>setNow(Date.now()),0);const timer=window.setInterval(()=>setNow(Date.now()),30000);return()=>{window.clearTimeout(initial);window.clearInterval(timer)}},[]);
 if(!review)return null;
 const command=`.venv/Scripts/python.exe -X utf8 -m pipeline.run --broker toss --approve ${review.id}`;
 const remaining=now===null?null:Math.max(0,Math.ceil((new Date(review.expiresAt).getTime()-now)/60000));
 const expired=remaining===0;
 async function copy(){try{await navigator.clipboard.writeText(command);setCopied(true);window.setTimeout(()=>setCopied(false),2500)}catch{setCopied(false)}}
 return <section className="panel inline-approval">
  <div className="approval-heading"><div><p className="eyebrow">FINAL STEP</p><h2>{expired?'주문안이 만료되었습니다.':'검토 후 직접 승인하세요.'}</h2><p>{expired?'최신 가격과 계좌 상태로 새 매매안을 만들어야 합니다.':'웹에서는 주문을 보내지 않습니다. 아래 명령을 복사해 본인 터미널에서 실행하면 주문 내용을 다시 확인합니다.'}</p></div><LockKeyhole/></div>
  <div className="approval-status"><span>계좌 <b>{review.account}</b></span><span>지정가 DAY <b>{review.orders.length}건</b></span><span className={expired?'negative':''}>{expired?'유효시간 종료':remaining===null?'유효시간 확인 중':`약 ${remaining}분 남음`}</span></div>
  <div className="approval-actions"><button className="primary-button" disabled={expired} onClick={copy}>{copied?<Check/>:<Clipboard/>}{copied?'복사했습니다':'터미널 승인 명령 복사'}</button><button className="secondary-button" onClick={()=>save(`approval-${review.id}.html`,exportHtml(review),'text/html')}><Download/>보고서 저장</button><button className="text-button" onClick={()=>save(`approval-${review.id}.json`,JSON.stringify(review,null,2),'application/json')}>JSON 저장</button></div>
  {!expired&&<details><summary>승인 명령 직접 보기</summary><pre>{command}</pre></details>}
  <p className="approval-footnote"><LockKeyhole/>터미널에서 정확한 승인 문구를 입력하기 전에는 주문이 전송되지 않습니다. 계좌나 가격이 달라지면 실행기가 승인을 거부합니다.</p>
 </section>;
}
