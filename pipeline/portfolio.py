"""Construct a quarterly allocation from validated AI research; never produce live orders."""
import datetime as dt, hashlib, json, os, sqlite3
from pathlib import Path
from .research import ROOT,domain,fingerprint,run_research

def select_candidates(fund_ids,count):
    context=domain({'action':'candidates','fundIds':fund_ids,'count':count})
    return context,context['rows'][:count]

def build_plan(fund_ids,budget=10000,cap=.2,cash=.1,count=8,run_missing=False):
    if not isinstance(count,int) or not 1<=count<=20: raise ValueError('count must be 1..20')
    context,candidates=select_candidates(fund_ids,count)
    if not candidates: raise ValueError('No eligible research candidates')
    reports=[];missing=[]
    for candidate in candidates:
        path=ROOT/'work/research'/(fingerprint(candidate['key'],fund_ids)+'.json')
        if path.exists(): report=json.loads(path.read_text(encoding='utf-8'))
        elif run_missing: report=run_research(candidate['key'],fund_ids)
        else: missing.append(candidate['ticker']);continue
        if report.get('status')!='completed' or report.get('period')!=context['period'] or sorted(report.get('fundIds',[]))!=sorted(fund_ids): raise ValueError('Stale or mismatched research context')
        reports.append(report)
    if missing: raise ValueError('AI research required first: '+', '.join(missing))
    buy_candidates={r['ticker'] for r in candidates if r['buyers']>=2 and r['buyers']>r['sellers']}
    scores={r['ticker']:r['decision']['score'] for r in reports if r['ticker'] in buy_candidates and r['decision']['stance']=='buy' and r['decision']['confidence']>=.65 and r['decision']['score']>=60 and not r['decision']['dataGaps']}
    allocation=domain({'action':'allocate','fundIds':fund_ids,'scores':scores,'budget':budget,'cap':cap,'cash':cash,'count':count})
    identity={'period':context['period'],'fundIds':sorted(fund_ids),'budget':budget,'cap':cap,'cash':cash,'count':count,'researchHashes':[fingerprint(r['key'],fund_ids) for r in reports]}
    plan_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    plan={'id':plan_id,'status':'completed','mode':'paper_allocation','period':context['period'],'createdAt':dt.datetime.now(dt.timezone.utc).isoformat(),'fundIds':sorted(fund_ids),'budgetUsd':budget,'constraints':{'maxWeight':cap,'minCash':cash,'maxHoldings':count,'minConfidence':.65,'minScore':60},'portfolio':allocation,'research':[{'ticker':r['ticker'],'decision':r['decision']} for r in reports],'excluded':[{'ticker':r['ticker'],'reason':'Non-buy / score / confidence / data gap gate'} for r in reports if r['ticker'] not in scores],'orders':[],'brokerConnected':False,'executionReady':False}
    output=ROOT/'work/portfolios';output.mkdir(parents=True,exist_ok=True)
    destination=output/(plan_id+'.json')
    if destination.exists(): return json.loads(destination.read_text(encoding='utf-8'))
    temp=destination.with_suffix('.tmp');temp.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(destination)
    return plan

def quarterly_once(config,collect_first=True):
    from .collect import collect
    # A quarterly run is an idempotent dry-run allocation, never a brokerage action.
    if collect_first: collect(os.getenv('SEC_USER_AGENT'))
    dataset=json.loads((ROOT/'data/filings.json').read_text(encoding='utf-8'))
    selected=config['fundIds'];ready={f['id'] for f in dataset['funds'] if f['status']=='ready'}
    if not set(selected).issubset(ready): raise ValueError('Configured fund has incomplete or suspect filings; keep previous plan')
    stable_data={k:v for k,v in dataset.items() if k!='generatedAt'}
    identity={'methodology':'quarterly-activity-v1','period':dataset['period'],'config':config,'dataHash':hashlib.sha256(json.dumps(stable_data,sort_keys=True).encode()).hexdigest(),'models':{k:os.getenv(k,'') for k in ('RESEARCH_PROVIDER','RESEARCH_DEEP_MODEL','RESEARCH_QUICK_MODEL')}}
    run_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    (ROOT/'work').mkdir(exist_ok=True)
    with sqlite3.connect(ROOT/'work/quarterly.sqlite',timeout=30) as db:
        db.execute('CREATE TABLE IF NOT EXISTS quarterly (id TEXT PRIMARY KEY,status TEXT NOT NULL,plan TEXT,error TEXT)')
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT status,plan FROM quarterly WHERE id=?',(run_id,)).fetchone()
        if row and row[0]=='completed': return json.loads(row[1])
        # The DB transaction holds a cross-process lock through research to prevent duplicates.
        db.execute('INSERT OR REPLACE INTO quarterly VALUES (?,?,?,?)',(run_id,'running',None,None))
        try:
            plan=build_plan(selected,config['budgetUsd'],config['maxWeight'],config['minCash'],config['maxHoldings'],True)
            db.execute('UPDATE quarterly SET status=?,plan=? WHERE id=?',('completed',json.dumps(plan),run_id));db.commit();return plan
        except Exception:
            db.rollback();raise
