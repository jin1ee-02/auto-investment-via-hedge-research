import { env } from 'cloudflare:workers';
export async function POST(request:Request){
 // Server-only bridge. No API keys or arbitrary backend URLs accepted from clients.
 const config=env as unknown as Record<string,string|undefined>;
 const origin=request.headers.get('origin');
 if(origin && origin!==new URL(request.url).origin)return Response.json({error:'다른 출처의 요청은 허용하지 않습니다.'},{status:403});
 if(!config.RESEARCH_SERVICE_URL||!config.RESEARCH_SERVICE_TOKEN)return Response.json({status:'not_configured',error:'AI 리서치 서비스가 아직 연결되지 않았습니다. 로컬 pipeline 서비스 또는 인증된 서버를 설정하세요. 현재 점수는 공시 기반 규칙 점수이며 AI 판단이 아닙니다.'},{status:503});
 const body=await request.json().catch(()=>null) as {fundIds?:unknown[];key?:string}|null;
 if(!body||!Array.isArray(body.fundIds)||body.fundIds.length<1||body.fundIds.length>30||!body.fundIds.every((v:unknown)=>typeof v==='string'&&/^[a-z0-9_-]+$/.test(v))||typeof body.key!=='string'||body.key.length>200)return Response.json({error:'잘못된 리서치 요청입니다.'},{status:400});
 try{const upstream=await fetch(new URL('/research',config.RESEARCH_SERVICE_URL),{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${config.RESEARCH_SERVICE_TOKEN}`},body:JSON.stringify({key:body.key,fundIds:body.fundIds}),signal:AbortSignal.timeout(120000)});
 const result=await upstream.json();return Response.json(result,{status:upstream.status});
 }catch{return Response.json({error:'리서치 서비스에 연결할 수 없습니다. 실행 중인 작업과 서버 설정을 확인하세요.'},{status:502});}
}
export async function GET(request:Request){
 const config=env as unknown as Record<string,string|undefined>;const id=new URL(request.url).searchParams.get('jobId');
 if(!id||!/^[a-f0-9]{64}$/.test(id))return Response.json({error:'잘못된 작업 ID'},{status:400});
 if(!config.RESEARCH_SERVICE_URL||!config.RESEARCH_SERVICE_TOKEN)return Response.json({error:'리서치 서버 미연결'},{status:503});
 try{const response=await fetch(new URL(`/jobs/${id}`,config.RESEARCH_SERVICE_URL),{headers:{Authorization:`Bearer ${config.RESEARCH_SERVICE_TOKEN}`},signal:AbortSignal.timeout(15000)});return Response.json(await response.json(),{status:response.status});}catch{return Response.json({error:'리서치 상태를 확인할 수 없습니다.'},{status:502});}
}
