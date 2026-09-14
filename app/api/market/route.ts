import {env} from 'cloudflare:workers';
export async function POST(request:Request){
 const origin=request.headers.get('origin');
 if(origin&&origin!==new URL(request.url).origin)return Response.json({error:'다른 출처의 요청입니다.'},{status:403});
 const config=env as unknown as Record<string,string|undefined>;
 if(!config.RESEARCH_SERVICE_URL||!config.RESEARCH_SERVICE_TOKEN)return Response.json({error:'시장 점검 서버가 연결되지 않았습니다.'},{status:503});
 const body=await request.json().catch(()=>null) as {keys?:unknown;fundIds?:unknown}|null;
 if(!body||!Array.isArray(body.keys)||body.keys.length<1||body.keys.length>8||!body.keys.every((k:unknown)=>typeof k==='string'&&k.length<=200)||!Array.isArray(body.fundIds)||body.fundIds.length<1||body.fundIds.length>30||!body.fundIds.every((id:unknown)=>typeof id==='string'&&/^[a-z0-9_-]+$/.test(id)))return Response.json({error:'점검할 후보를 1~8개 선택하세요.'},{status:400});
 try{
  const response=await fetch(new URL('/market',config.RESEARCH_SERVICE_URL),{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${config.RESEARCH_SERVICE_TOKEN}`},body:JSON.stringify({keys:body.keys,fundIds:body.fundIds}),signal:AbortSignal.timeout(180000)});
  return Response.json(await response.json(),{status:response.status,headers:{'Cache-Control':'no-store'}});
 }catch{return Response.json({error:'시장 점검 서버에 연결하지 못했습니다. Python 서비스를 실행하고 다시 시도하세요.'},{status:502})}
}
