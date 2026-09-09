import {env} from 'cloudflare:workers';
export async function GET(request:Request){
 const config=env as unknown as Record<string,string|undefined>;
 if(config.RESEARCH_SERVICE_URL&&config.RESEARCH_SERVICE_TOKEN){try{const response=await fetch(new URL('/filings',config.RESEARCH_SERVICE_URL),{headers:{Authorization:`Bearer ${config.RESEARCH_SERVICE_TOKEN}`},signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error();return Response.json(await response.json(),{headers:{'Cache-Control':'no-store'}})}catch{return Response.json({error:'Latest filing service unavailable; keep existing snapshot'},{status:502})}}
 return Response.redirect(new URL('/filings.json',request.url),307)
}
