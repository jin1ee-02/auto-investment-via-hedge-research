"""Authenticated loopback job service; serial AI jobs, SQLite persistence, no trading."""
import argparse,concurrent.futures,contextlib,hmac,json,os,re,sqlite3,threading,time,traceback,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .research import ROOT,load_env,provider_config,domain,fingerprint,run_research,ReportTruncatedError
from .portfolio import build_account_plan,select_candidates

POOL=concurrent.futures.ThreadPoolExecutor(max_workers=1)
LOCK=threading.Lock()
DEFAULT_CANDIDATE_COUNT=6
MAX_CANDIDATE_COUNT=8
TRANSIENT_RESEARCH_ERRORS={'OpenAIConnectionError','APIConnectionError','APITimeoutError','RateLimitError','TimeoutError','ConnectionError'}

@contextlib.contextmanager
def database():
    (ROOT/'work').mkdir(exist_ok=True)
    db=sqlite3.connect(ROOT/'work/jobs.sqlite',timeout=20)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,status TEXT NOT NULL,result TEXT NOT NULL)')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_job(job_id):
    with database() as db:
        row=db.execute('SELECT result FROM jobs WHERE id=?',(job_id,)).fetchone()
    return json.loads(row[0]) if row else None

def save_job(job_id,result):
    with database() as db: db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)',(job_id,result['status'],json.dumps({**result,'jobId':job_id},ensure_ascii=False)))

def active_pipeline():
    with database() as db:
        rows=db.execute("SELECT result FROM jobs WHERE status IN ('queued','running') ORDER BY rowid DESC").fetchall()
    for (raw,) in rows:
        value=json.loads(raw)
        if value.get('kind')=='pipeline':return value
    return None

def worker(job_id,key,ids,identity=None):
    identity=identity or {'key':key,'fundIds':ids}
    save_job(job_id,{'status':'running',**identity})
    last={}
    def update(progress):
        last['progress']=progress
        save_job(job_id,{'status':'running',**identity,**last})
    try: save_job(job_id,{**run_research(key,ids,on_progress=update),**last})
    except Exception as exc:
        # Do not serialize provider HTTP errors, which can contain credentials or request data.
        error='보고서가 모델 출력 한도에 도달했습니다. RESEARCH_MAX_TOKENS를 높이고 서비스를 재시작한 후 다시 조사하세요. 불완전한 결과는 포트폴리오에 반영하지 않았습니다.' if isinstance(exc,ReportTruncatedError) else f'AI 리서치를 완료하지 못했습니다 ({type(exc).__name__}). 잠시 후 다시 시도하거나 서버 진단을 확인하세요.'
        save_job(job_id,{'status':'failed',**identity,**last,'error':error})

def enqueue(key,ids):
    provider_config() # Reject missing API setup before creating a misleading job.
    context=domain({'action':'candidates','fundIds':ids})
    eligible={row['key']:row for row in context['rows']}
    if key not in eligible: raise ValueError('Unknown or unavailable candidate')
    job_id=fingerprint(key,ids)
    with LOCK:
        existing=get_job(job_id)
        if existing and existing['status'] in ('completed','queued','running'):return existing
        with database() as db:
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]>=8:raise ValueError('Research queue full; wait for existing jobs')
        identity={'key':key,'ticker':eligible[key]['ticker'],'fundIds':sorted(ids)}
        save_job(job_id,{'status':'queued',**identity});POOL.submit(worker,job_id,key,ids,identity)
    return {'status':'queued','jobId':job_id,'ticker':eligible[key]['ticker']}

def _public_review(review):
    return {'schemaVersion':review['schemaVersion'],'id':review['id'],'status':review['status'],'account':'••••'+str(review['account'])[-4:],'createdAt':review['createdAt'],'expiresAt':review['expiresAt'],'orders':review['orders'],'plan':review['plan']}

def _run_research_with_retry(key,ids,on_progress=None):
    """Retry only transient provider/network failures; completed reports remain cacheable."""
    for attempt in range(3):
        try:return run_research(key,ids,on_progress=on_progress)
        except Exception as exc:
            if type(exc).__name__ not in TRANSIENT_RESEARCH_ERRORS or attempt==2:raise
            time.sleep(2**attempt)

def _pipeline_error(exc,stage):
    if type(exc).__name__ in TRANSIENT_RESEARCH_ERRORS:
        return 'AI 서비스 연결이 세 차례 실패했습니다. 완료된 보고서는 보존되었습니다. 네트워크 연결을 확인한 뒤 다시 실행하세요.'
    if stage=='account':
        return f'리서치는 완료했지만 계좌 기반 매매안을 만들지 못했습니다: {str(exc)[:400]}'
    return f'종목 리서치를 완료하지 못했습니다: {str(exc)[:400]}'

def pipeline_worker(run_id,ids,candidate_filter,candidates):
    identity={'kind':'pipeline','runId':run_id,'fundIds':sorted(ids),'candidateFilter':candidate_filter,'candidateCount':len(candidates),'selectedCandidates':[{'key':c['key'],'ticker':c['ticker'],'buyers':c['buyers'],'sellers':c['sellers'],'holders':c['holders']} for c in candidates]}
    reports=[]
    try:
        save_job(run_id,{'status':'running','stage':'research',**identity,'research':reports})
        for index,candidate in enumerate(candidates):
            def update(progress,candidate=candidate,index=index):
                save_job(run_id,{'status':'running','stage':'research',**identity,'research':reports,'currentCandidate':{'index':index+1,'total':len(candidates),'ticker':candidate['ticker'],'progress':progress}})
            report=_run_research_with_retry(candidate['key'],ids,on_progress=update);reports.append(report)
            save_job(run_id,{'status':'running','stage':'research',**identity,'research':reports,'currentCandidate':{'index':index+1,'total':len(candidates),'ticker':candidate['ticker'],'status':'cached' if report.get('cacheHit') else 'completed'}})
        from .toss import TossBroker
        broker=TossBroker()
        config=json.loads((ROOT/'pipeline/strategy.json').read_text(encoding='utf-8'))
        config.update(fundIds=sorted(ids),candidateFilter=candidate_filter)
        save_job(run_id,{'status':'running','stage':'account',**identity,'research':reports})
        plan=build_account_plan(ids,candidates,reports,broker,config,run_id)
        proposal_status='ready';review=None
        try:
            from .execution import draft_orders
            orders=draft_orders(plan,broker,config);plan['orders']=orders
            if orders:
                plan['proposalStatus']='ready';plan['executionReady']=True
                from .approval import prepare_review
                review=_public_review(prepare_review(plan,broker,config,orders))
            else:
                proposal_status='no_orders';plan['proposalStatus']=proposal_status;plan['executionReady']=False
        except ValueError as exc:
            message=str(exc)
            proposal_status='waiting_for_fresh_quote' if any(word in message.lower() for word in ('quote','trading session','expired')) else 'blocked'
            plan.update(proposalStatus=proposal_status,proposalMessage=message,executionReady=False)
        destination=ROOT/'work/portfolios'/(plan['id']+'.json');temp=destination.with_suffix('.tmp')
        temp.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(destination)
        save_job(run_id,{'status':'completed','stage':'proposal','proposalStatus':proposal_status,**identity,'research':reports,'plan':plan,'review':review})
    except Exception as exc:
        stage='research' if len(reports)<len(candidates) else 'account'
        save_job(run_id,{'status':'failed','stage':stage,**identity,'research':reports,'error':_pipeline_error(exc,stage),'errorType':type(exc).__name__})

def enqueue_pipeline(ids,candidate_filter=None,candidate_count=DEFAULT_CANDIDATE_COUNT):
    # Reattach before validating a new request so refreshes or changed UI filters
    # can never hide the one server-owned pipeline that is already in progress.
    with LOCK:
        active=active_pipeline()
        if active:return {**active,'resumed':True}
    provider_config()
    if type(candidate_count) is not int or not 1<=candidate_count<=MAX_CANDIDATE_COUNT:raise ValueError('candidateCount must be 1..8')
    candidate_filter=candidate_filter or {'direction':'all','minFunds':2,'includeMixed':True}
    _,candidates=select_candidates(ids,candidate_count,candidate_filter);candidates=candidates[:candidate_count]
    if not candidates:raise ValueError('No eligible research candidates')
    run_id=uuid.uuid4().hex
    with LOCK:
        active=active_pipeline()
        if active:return {**active,'resumed':True}
        result={'status':'queued','kind':'pipeline','runId':run_id,'fundIds':sorted(ids),'candidateFilter':candidate_filter,'candidateCount':len(candidates),'selectedCandidates':[{'key':c['key'],'ticker':c['ticker'],'buyers':c['buyers'],'sellers':c['sellers'],'holders':c['holders']} for c in candidates]}
        save_job(run_id,result);POOL.submit(pipeline_worker,run_id,ids,candidate_filter,candidates)
    return result

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
        if self.path=='/pipelines/active':
            job=active_pipeline();return self.send(200 if job else 404,job or {'error':'No active pipeline'})
        if re.fullmatch(r'/jobs/[a-f0-9]{64}',self.path):
            job=get_job(self.path.split('/')[-1]);return self.send(200 if job else 404,job or {'error':'Unknown job'})
        if re.fullmatch(r'/pipelines/[a-f0-9]{32}',self.path):
            job=get_job(self.path.split('/')[-1]);return self.send(200 if job and job.get('kind')=='pipeline' else 404,job or {'error':'Unknown pipeline'})
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
            if self.path=='/research':
                key=body.get('key')
                if not isinstance(key,str) or len(key)>200:raise ValueError('Invalid security key')
                result=enqueue(key,ids);self.send(200 if result['status']=='completed' else 202,result)
            elif self.path=='/pipelines':
                result=enqueue_pipeline(ids,body.get('candidateFilter'),body.get('candidateCount',DEFAULT_CANDIDATE_COUNT));self.send(202,result)
            else:self.send(404,{'error':'Not found'})
        except (ValueError,KeyError,RuntimeError) as exc:self.send(409,{'error':str(exc)[:1000]})
        except Exception as exc:
            traceback.print_exc()
            self.send(500,{'error':f'리서치 작업 생성 중 내부 오류가 발생했습니다 ({type(exc).__name__}). 서버 로그를 확인하세요.'})

def main():
    load_env();parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8788);args=parser.parse_args()
    if len(os.getenv('RESEARCH_SERVICE_TOKEN',''))<32:raise RuntimeError('Set a random RESEARCH_SERVICE_TOKEN of at least 32 characters')
    with database() as db:
        pending=db.execute("SELECT id,result FROM jobs WHERE status IN ('running','queued')").fetchall()
    for job_id,raw in pending:
        saved=json.loads(raw);save_job(job_id,{**saved,'status':'failed','error':'Service restarted. Retry to resume saved research or pipeline.'})
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Hedge Insight research service: http://127.0.0.1:{args.port} (token required, trading disabled)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();POOL.shutdown(wait=False,cancel_futures=True)

if __name__=='__main__':main()
