import {env} from 'cloudflare:workers';
import {validateCandidateFilter,type CandidateFilter} from '@/lib/domain';

function config(){return env as unknown as Record<string,string|undefined>}
function sameOrigin(request:Request){const origin=request.headers.get('origin');return !origin||origin===new URL(request.url).origin}

export async function POST(request:Request){
 if(!sameOrigin(request))return Response.json({error:'다른 출처의 요청은 허용하지 않습니다.'},{status:403});
 const settings=config();
 if(!settings.RESEARCH_SERVICE_URL||!settings.RESEARCH_SERVICE_TOKEN)return Response.json({error:'리서치 서비스가 연결되지 않았습니다.'},{status:503});
 const body=await request.json().catch(()=>null) as {fundIds?:unknown[];candidateFilter?:CandidateFilter;candidateCount?:unknown}|null;
 if(!body||!Array.isArray(body.fundIds)||!body.fundIds.length||body.fundIds.length>30||!body.fundIds.every(id=>typeof id==='string'&&/^[a-z0-9_-]+$/.test(id)))return Response.json({error:'펀드 선택을 확인하세요.'},{status:400});
 if(body.candidateFilter!==undefined){try{validateCandidateFilter(body.candidateFilter)}catch{return Response.json({error:'후보 조건을 확인하세요.'},{status:400})}}
 if(body.candidateCount!==undefined&&(!Number.isInteger(body.candidateCount)||Number(body.candidateCount)<1||Number(body.candidateCount)>8))return Response.json({error:'리서치 종목 수는 1~8개로 선택하세요.'},{status:400});
 try{const response=await fetch(new URL('/pipelines',settings.RESEARCH_SERVICE_URL),{method:'POST',headers:{Authorization:`Bearer ${settings.RESEARCH_SERVICE_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(30000)});return Response.json(await response.json(),{status:response.status,headers:{'Cache-Control':'no-store'}})}catch{return Response.json({error:'파이프라인 서비스를 시작할 수 없습니다.'},{status:502})}
}

export async function GET(request:Request){
 if(!sameOrigin(request))return Response.json({error:'다른 출처의 요청은 허용하지 않습니다.'},{status:403});
 const settings=config(),params=new URL(request.url).searchParams,runId=params.get('runId'),active=params.get('active')==='1';
 if(!active&&(!runId||!/^[a-f0-9]{32}$/.test(runId)))return Response.json({error:'잘못된 실행 ID입니다.'},{status:400});
 if(!settings.RESEARCH_SERVICE_URL||!settings.RESEARCH_SERVICE_TOKEN)return Response.json({error:'리서치 서비스가 연결되지 않았습니다.'},{status:503});
 try{const response=await fetch(new URL(active?'/pipelines/active':`/pipelines/${runId}`,settings.RESEARCH_SERVICE_URL),{headers:{Authorization:`Bearer ${settings.RESEARCH_SERVICE_TOKEN}`},signal:AbortSignal.timeout(15000)});return Response.json(await response.json(),{status:response.status,headers:{'Cache-Control':'no-store'}})}catch{return Response.json({error:'파이프라인 상태를 확인할 수 없습니다.'},{status:502})}
}
