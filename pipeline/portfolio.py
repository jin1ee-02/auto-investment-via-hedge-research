"""Construct validated research allocations; never submit brokerage orders."""
import datetime as dt, hashlib, json, os, sqlite3, uuid
from decimal import Decimal
from pathlib import Path
from contextlib import closing
from .research import ROOT,domain,fingerprint,run_research,blocking_data_gaps

def _rating_strength(value):
    value=str(value or '').lower()
    if 'overweight' in value or 'underweight' in value:return 80
    if value.strip() in ('buy','sell'):return 100
    return 0

def select_candidates(fund_ids,count=None,candidate_filter=None):
    payload={'action':'candidates','fundIds':fund_ids}
    if count is not None:payload['count']=count
    if candidate_filter is not None:payload['candidateFilter']=candidate_filter
    context=domain(payload)
    return context,context['rows']

def build_plan(fund_ids,budget=10000,cap=.2,cash=.1,count=8,run_missing=False,candidate_filter=None):
    if not isinstance(count,int) or not 1<=count<=20: raise ValueError('count must be 1..20')
    context,candidates=select_candidates(fund_ids,count,candidate_filter);candidates=candidates[:count]
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
    scores={r['ticker']:_rating_strength(r.get('upstreamSignal')) for r in reports if r['ticker'] in buy_candidates and _signal(r.get('upstreamSignal'))=='buy' and not blocking_data_gaps(r.get('decision',{}).get('dataGaps'))}
    allocation=domain({'action':'allocate','fundIds':fund_ids,'scores':scores,'budget':budget,'cap':cap,'cash':cash,'count':count,'candidateFilter':candidate_filter} if candidate_filter is not None else {'action':'allocate','fundIds':fund_ids,'scores':scores,'budget':budget,'cap':cap,'cash':cash,'count':count})
    identity={'period':context['period'],'fundIds':sorted(fund_ids),'budget':budget,'cap':cap,'cash':cash,'count':count,'researchHashes':[fingerprint(r['key'],fund_ids) for r in reports]}
    identity['candidateFilter']=candidate_filter
    plan_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    plan={'id':plan_id,'status':'completed','mode':'paper_allocation','period':context['period'],'createdAt':dt.datetime.now(dt.timezone.utc).isoformat(),'fundIds':sorted(fund_ids),'budgetUsd':budget,'constraints':{'maxWeight':cap,'minCash':cash,'maxHoldings':count},'portfolio':allocation,'research':[{'ticker':r['ticker'],'decision':r['decision'],'upstreamSignal':r.get('upstreamSignal')} for r in reports],'excluded':[{'ticker':r['ticker'],'reason':'TradingAgents direction or critical data integrity gate'} for r in reports if r['ticker'] not in scores],'orders':[],'brokerConnected':False,'executionReady':False}
    output=ROOT/'work/portfolios';output.mkdir(parents=True,exist_ok=True)
    plan['candidateFilter']=candidate_filter or {'direction':'all','minFunds':2,'includeMixed':True}
    plan['candidateCount']=len(candidates)
    destination=output/(plan_id+'.json')
    if destination.exists(): return json.loads(destination.read_text(encoding='utf-8'))
    temp=destination.with_suffix('.tmp');temp.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(destination)
    return plan

def _signal(value):
    value=str(value or '').upper()
    if 'UNDERWEIGHT' in value or 'SELL' in value:return 'sell'
    if 'OVERWEIGHT' in value or 'BUY' in value:return 'buy'
    return 'hold'

def _allocate_account_targets(scored,capital,protected,held_symbols,config):
    """Water-fill eligible targets while leaving protected holdings untouched."""
    capital=Decimal(str(capital));protected=Decimal(str(protected))
    available=max(Decimal(0),capital*(Decimal(1)-Decimal(str(config['minCash'])))-protected)
    cap=capital*Decimal(str(config['maxWeight']))
    existing=[row for row in scored if row['ticker'] in held_symbols]
    new=[row for row in scored if row['ticker'] not in held_symbols]
    slots=max(0,config['maxHoldings']-len(held_symbols))
    selected=existing+new[:slots]
    weights={row['ticker']:Decimal(0) for row in selected};active=list(selected);remaining=available
    while active and remaining>Decimal('0.000001'):
        total=sum(Decimal(str(row['allocationScore'])) for row in active)
        if total<=0:break
        used=Decimal(0);next_active=[]
        for row in active:
            ticker=row['ticker'];room=max(Decimal(0),cap-weights[ticker])
            add=min(room,remaining*Decimal(str(row['allocationScore']))/total)
            weights[ticker]+=add;used+=add
            if room-add>Decimal('0.000001'):next_active.append(row)
        remaining-=used
        if used<=Decimal('0.000001'):break
        active=next_active
    return [{'ticker':row['ticker'],'amount':float(weights[row['ticker']].quantize(Decimal('.01'))),'weight':float(weights[row['ticker']]/capital) if capital else 0,'allocationScore':row['allocationScore']} for row in selected]

def build_account_plan(fund_ids,candidates,reports,broker,config,run_id):
    """Build a US-only proposal from a fresh Toss account snapshot."""
    from .execution import number,validate_config
    validate_config(config)
    if len(candidates)>8 or len(reports)!=len(candidates):raise ValueError('A complete research set of at most eight candidates is required')
    periods={report.get('period') for report in reports}
    candidate_keys={candidate.get('key') for candidate in candidates}
    if len(candidate_keys)!=len(candidates) or {report.get('key') for report in reports}!=candidate_keys or len(periods)!=1 or any(report.get('status')!='completed' or sorted(report.get('fundIds',[]))!=sorted(fund_ids) for report in reports):
        raise ValueError('Every selected candidate needs complete, matching research')
    holdings=broker.get('holdings')
    if not isinstance(holdings,dict) or not isinstance(holdings.get('items'),list):raise ValueError('Invalid holdings response')
    power=broker.get('buying-power',currency='USD')
    if power.get('currency')!='USD':raise ValueError('Unexpected buying-power currency')
    cash=number(power.get('cashBuyingPower'))
    us_items=[item for item in holdings['items'] if item.get('marketCountry')=='US' and item.get('currency')=='USD']
    excluded_items=[item for item in holdings['items'] if item.get('marketCountry')!='US' or item.get('currency')!='USD']
    kr_items=[item for item in excluded_items if item.get('marketCountry')=='KR']
    held={};values={}
    for item in us_items:
        ticker=item.get('symbol')
        if not isinstance(ticker,str) or ticker in held:raise ValueError('Invalid or duplicate US holding')
        held[ticker]=number(item.get('quantity'))
        market=item.get('marketValue') or {}
        values[ticker]=number(market['amount']) if market.get('amount') is not None else number(item.get('lastPrice'))*held[ticker]
    capital=cash+sum(values.values(),Decimal(0))
    selected={row['ticker']:row for row in candidates}
    enriched=[];buy_rows=[];actionable=set()
    for report in reports:
        ticker=report['ticker'];candidate=selected[ticker];decision=report['decision'];signal=_signal(report.get('upstreamSignal'))
        blocking_gaps=blocking_data_gaps(decision['dataGaps'])
        complete=not blocking_gaps
        if complete and candidate['buyers']>candidate['sellers'] and signal=='buy':
            action='buy';reason='Expansion consensus and TradingAgents Buy/Overweight agree'
        elif complete and candidate['sellers']>candidate['buyers'] and signal=='sell' and ticker in held:action='sell';reason='Reduction consensus and TradingAgents Sell/Underweight agree for a held US position'
        else:
            action='hold'
            if blocking_gaps:reason=f"Research has {len(blocking_gaps)} critical data integrity gaps"
            elif signal=='hold':reason='TradingAgents signal is neutral or unrecognized'
            elif candidate['buyers']==candidate['sellers']:reason='Fund directions are tied'
            elif candidate['buyers']>candidate['sellers']:reason='Expansion consensus conflicts with TradingAgents direction'
            elif ticker not in held:reason='Reduction candidate is not a currently held US position'
            else:reason='Reduction consensus conflicts with TradingAgents direction'
        same=max(candidate['buyers'],candidate['sellers'])
        allocation_score=_rating_strength(report.get('upstreamSignal'))*(same/len(fund_ids)) if action=='buy' else 0
        item={'ticker':ticker,'key':report['key'],'decision':decision,'blockingDataGaps':blocking_gaps,'limitations':[gap for gap in decision['dataGaps'] if gap not in blocking_gaps],'upstreamSignal':report.get('upstreamSignal'),'candidate':{'buyers':candidate['buyers'],'sellers':candidate['sellers'],'holders':candidate['holders'],'sameDirectionFunds':same},'action':action,'actionReason':reason,'allocationScore':round(allocation_score,6)}
        enriched.append(item)
        if action=='buy':buy_rows.append(item);actionable.add(ticker)
        if action=='sell':actionable.add(ticker)
    protected_symbols=set(held)-actionable
    protected=sum((values[s] for s in protected_symbols),Decimal(0))
    cap_amount=capital*Decimal(str(config['maxWeight']))
    existing_limit_exceeded=len(held)>config['maxHoldings'] or any(value>cap_amount for value in values.values())
    allocatable_rows=[row for row in buy_rows if not existing_limit_exceeded or row['ticker'] in held]
    targets=_allocate_account_targets(sorted(allocatable_rows,key=lambda x:(-x['allocationScore'],x['ticker'])),capital,protected,set(held),config)
    for target in targets:
        current=values.get(target['ticker'],Decimal(0))
        if current>Decimal(str(target['amount'])):
            target['amount']=float(current.quantize(Decimal('.01')))
            target['weight']=float(current/capital) if capital else 0
    target_map={p['ticker'] for p in targets}
    excluded=[]
    for item in enriched:
        if item['action']=='buy' and item['ticker'] not in target_map:reason='Existing holding limit blocks new positions' if existing_limit_exceeded and item['ticker'] not in held else 'No available holding slot or investable capital'
        elif item['action']=='hold':reason=item['actionReason']
        elif item['action']=='sell':continue
        else:continue
        excluded.append({'ticker':item['ticker'],'reason':reason})
    now=dt.datetime.now(dt.timezone.utc).isoformat();batch_id=uuid.uuid4().hex
    excluded_assets=[{'symbol':item.get('symbol'),'marketCountry':item.get('marketCountry'),'currency':item.get('currency'),'marketValue':str((item.get('marketValue') or {}).get('amount','unknown'))} for item in excluded_items]
    account_snapshot={'asOf':now,'account':'••••'+str(broker.account)[-4:],'usdCashBuyingPower':str(cash),'usHoldingsValue':str(sum(values.values(),Decimal(0))),'usCapitalUsd':str(capital),'protectedHoldingsValue':str(protected),'usHoldingCount':len(us_items),'excludedKrHoldingCount':len(kr_items),'excludedAssets':excluded_assets}
    identity={'runId':run_id,'batchId':batch_id,'period':reports[0]['period'] if reports else None,'fundIds':sorted(fund_ids),'account':str(broker.account),'accountSnapshot':account_snapshot,'researchHashes':[fingerprint(r['key'],fund_ids) for r in reports],'targets':targets,'config':config}
    plan_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    plan={'id':plan_id,'runId':run_id,'batchId':batch_id,'status':'completed','mode':'account_proposal','period':identity['period'],'createdAt':now,'fundIds':sorted(fund_ids),'accountSnapshot':account_snapshot,'constraints':{'maxWeight':config['maxWeight'],'minCash':config['minCash'],'maxHoldings':config['maxHoldings'],'maxTurnover':config['maxTurnover'],'minTradeUsd':config['minTradeUsd'],'feeBuffer':config['feeBuffer']},'portfolio':{'positions':targets,'protectedHoldingsValue':str(protected),'cashTarget':str(max(Decimal(0),capital-sum((Decimal(str(p['amount'])) for p in targets),Decimal(0))-protected))},'research':enriched,'excluded':excluded,'orders':[],'brokerConnected':True,'executionReady':False,'strategyConfig':config}
    output=ROOT/'work/portfolios';output.mkdir(parents=True,exist_ok=True)
    destination=output/(plan_id+'.json');temp=destination.with_suffix('.tmp')
    temp.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(destination)
    return plan

def quarterly_once(config,collect_first=True):
    from .collect import collect
    from .execution import validate_config
    validate_config(config)
    # A quarterly run is an idempotent dry-run allocation, never a brokerage action.
    if collect_first: collect(os.getenv('SEC_USER_AGENT'))
    dataset=json.loads((ROOT/'data/filings.json').read_text(encoding='utf-8'))
    selected=config['fundIds'];ready={f['id'] for f in dataset['funds'] if f['status']=='ready'}
    if not set(selected).issubset(ready): raise ValueError('Configured fund has incomplete or suspect filings; keep previous plan')
    period=dt.date.fromisoformat(dataset['period'])
    today=dt.date.today()
    expected=today.replace(month=3*((today.month-1)//3)+1,day=1)-dt.timedelta(days=1)
    if period!=expected or dataset['period']<config['startPeriod']:
        raise ValueError('Waiting for the configured new filing quarter')
    for fund in dataset['funds']:
        if fund['id'] in selected:
            for p in (dataset['period'],dataset['previousPeriod']):
                snapshots=[s for s in fund['snapshots'] if s['period']==p and s['complete']]
                if len(snapshots)!=1 or not p<=snapshots[0]['filedAt']<=today.isoformat():
                    raise ValueError('Missing or invalid filing pair')
    run_id='quarter-v2:'+dataset['period']
    (ROOT/'work').mkdir(exist_ok=True)
    with closing(sqlite3.connect(ROOT/'work/quarterly.sqlite',timeout=30)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS quarterly (id TEXT PRIMARY KEY,status TEXT NOT NULL,plan TEXT,error TEXT)')
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT status,plan FROM quarterly WHERE id=?',(run_id,)).fetchone()
        if row and row[0]=='completed': return json.loads(row[1])
        if row: raise ValueError('Quarter research interrupted; inspect saved state before recovery')
        # The DB transaction holds a cross-process lock through research to prevent duplicates.
        db.execute('INSERT INTO quarterly VALUES (?,?,?,?)',(run_id,'running',None,None))
        db.commit()
        try:
            _,candidates=select_candidates(selected,candidate_filter=config.get('candidateFilter'))
            if candidates:
                plan=build_plan(selected,config['budgetUsd'],config['maxWeight'],config['minCash'],config['maxHoldings'],True,config.get('candidateFilter'))
            else:
                plan={'id':run_id,'period':dataset['period'],'status':'completed','createdAt':dt.datetime.now(dt.timezone.utc).isoformat(),'portfolio':{'positions':[]},'research':[],'orders':[]}
            current=json.loads((ROOT/'data/filings.json').read_text(encoding='utf-8'))
            def selected_snapshot(data):
                return {'period':data['period'],'previousPeriod':data['previousPeriod'],'funds':sorted([f for f in data['funds'] if f['id'] in selected],key=lambda f:f['id'])}
            if selected_snapshot(current)!=selected_snapshot(dataset) or plan['period']!=dataset['period']:
                raise ValueError('Filing data changed during research; no mixed-snapshot execution')
            plan['strategyConfig']=config
            plan['trigger']={'type':'complete_new_filing_quarter','period':dataset['period'],'fundIds':sorted(selected)}
            plan['filingSnapshotHash']=hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest()
            db.execute('UPDATE quarterly SET status=?,plan=? WHERE id=?',('completed',json.dumps(plan),run_id));db.commit();return plan
        except Exception:
            db.execute('UPDATE quarterly SET status=?,error=? WHERE id=?',('failed','Research failed; inspect before explicit recovery',run_id));db.commit();raise
