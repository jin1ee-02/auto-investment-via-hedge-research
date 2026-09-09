import {env} from 'cloudflare:workers';
export async function POST(request:Request){
 const origin=request.headers.get('origin');if(origin&&origin!==new URL(request.url).origin)return Response.json({error:'Origin mismatch'},{status:403});
 const config=env as unknown as Record<string,string|undefined>;
 if(!config.RESEARCH_SERVICE_URL||!config.RESEARCH_SERVICE_TOKEN)return Response.json({error:'AI 리서치 서버가 연결되지 않았습니다. API 설정 후 사용하세요.'},{status:503});
 const body=await request.json().catch(()=>null) as {fundIds?:unknown[];budget?:number;cap?:number;cash?:number;count?:number}|null;
 if(!body||!Array.isArray(body.fundIds)||body.fundIds.length<1||body.fundIds.length>30||!body.fundIds.every(id=>typeof id==='string'&&/^[a-z0-9_-]+$/.test(id))||!Number.isFinite(body.budget)||!Number.isFinite(body.cap)||!Number.isFinite(body.cash)||!Number.isInteger(body.count))return Response.json({error:'잘못된 배분 조건'},{status:400});
 try{const response=await fetch(new URL('/portfolio',config.RESEARCH_SERVICE_URL),{method:'POST',headers:{Authorization:`Bearer ${config.RESEARCH_SERVICE_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(30000)});return Response.json(await response.json(),{status:response.status});}catch{return Response.json({error:'AI 배분안을 불러올 수 없습니다.'},{status:502});}
}
