"""Authenticated loopback job service; serial AI jobs, SQLite persistence, no trading."""
import argparse,concurrent.futures,hmac,json,os,re,sqlite3,threading,traceback
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .research import ROOT,load_env,provider_config,domain,fingerprint,run_research
from .portfolio import build_plan

POOL=concurrent.futures.ThreadPoolExecutor(max_workers=1)
LOCK=threading.Lock()

def database():
    (ROOT/'work').mkdir(exist_ok=True)
    db=sqlite3.connect(ROOT/'work/jobs.sqlite',timeout=20)
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,status TEXT NOT NULL,result TEXT NOT NULL)')
    return db

def get_job(job_id):
    with database() as db:
        row=db.execute('SELECT result FROM jobs WHERE id=?',(job_id,)).fetchone()
    return json.loads(row[0]) if row else None

def save_job(job_id,result):
    with database() as db: db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)',(job_id,result['status'],json.dumps({**result,'jobId':job_id},ensure_ascii=False)))

def worker(job_id,key,ids):
    save_job(job_id,{'status':'running'})
    last={}
    def update(progress):
        last['progress']=progress
        save_job(job_id,{'status':'running',**last})
    try: save_job(job_id,{**run_research(key,ids,on_progress=update),**last})
    except Exception as exc:
        # Do not serialize provider HTTP errors, which can contain credentials or request data.
        save_job(job_id,{'status':'failed',**last,'error':f'AI research failed ({type(exc).__name__}); check provider settings and server diagnostics.'})

def enqueue(key,ids):
    provider_config() # Reject missing API setup before creating a misleading job.
    context=domain({'action':'candidates','fundIds':ids})
    if not any(row['key']==key for row in context['rows']): raise ValueError('Unknown or unavailable candidate')
    job_id=fingerprint(key,ids)
    with LOCK:
        existing=get_job(job_id)
        if existing and existing['status'] in ('completed','queued','running'):return existing
        with database() as db:
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]>=8:raise ValueError('Research queue full; wait for existing jobs')
        save_job(job_id,{'status':'queued'});POOL.submit(worker,job_id,key,ids)
    return {'status':'queued','jobId':job_id}

class Handler(BaseHTTPRequestHandler):
    server_version='HedgeInsight/1.0'
    def log_message(self,*args): pass
    def auth(self):
        expected='Bearer '+os.environ['RESEARCH_SERVICE_TOKEN']
        return hmac.compare_digest(self.headers.get('Authorization',''),expected)
    def send(self,status,body):
        raw=json.dumps(body,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if not self.auth():return self.send(401,{'error':'Unauthorized'})
        if self.path=='/health':return self.send(200,{'status':'ok','brokerConnected':False})
        if self.path=='/filings':return self.send(200,json.loads((ROOT/'data/filings.json').read_text(encoding='utf-8')))
        if re.fullmatch(r'/jobs/[a-f0-9]{64}',self.path):
            job=get_job(self.path.split('/')[-1]);return self.send(200 if job else 404,job or {'error':'Unknown job'})
        self.send(404,{'error':'Not found'})
    def do_POST(self):
        if not self.auth():return self.send(401,{'error':'Unauthorized'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=32768:raise ValueError('Invalid payload size')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('Expected JSON object')
            ids=body.get('fundIds')
            if not isinstance(ids,list) or not 1<=len(ids)<=30 or any(not isinstance(v,str) or not re.fullmatch(r'[a-z0-9_-]+',v) for v in ids):raise ValueError('Invalid fund IDs')
            if self.path=='/market':
                from .market import market_batch
                self.send(200,market_batch(body.get('keys'),ids))
            elif self.path=='/research':
                key=body.get('key')
                if not isinstance(key,str) or len(key)>200:raise ValueError('Invalid security key')
                result=enqueue(key,ids);self.send(200 if result['status']=='completed' else 202,result)
            elif self.path=='/portfolio':
                result=build_plan(ids,float(body['budget']),float(body['cap']),float(body['cash']),int(body['count']),False);self.send(200,result)
            else:self.send(404,{'error':'Not found'})
        except (ValueError,KeyError,RuntimeError) as exc:self.send(409,{'error':str(exc)[:1000]})
        except Exception:self.send(500,{'error':'Internal job error; check configuration'})

def main():
    load_env();parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8788);args=parser.parse_args()
    if len(os.getenv('RESEARCH_SERVICE_TOKEN',''))<32:raise RuntimeError('Set a random RESEARCH_SERVICE_TOKEN of at least 32 characters')
    with database() as db:
        pending=db.execute("SELECT id FROM jobs WHERE status IN ('running','queued')").fetchall()
    for (job_id,) in pending:save_job(job_id,{'status':'failed','error':'Service restarted. Retry to resume saved research.'})
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Hedge Insight research service: http://127.0.0.1:{args.port} (token required, trading disabled)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();POOL.shutdown(wait=False,cancel_futures=True)

if __name__=='__main__':main()
