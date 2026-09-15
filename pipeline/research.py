"""TradingAgents research for hedge-consensus candidates. Never places an order."""
import datetime as dt, hashlib, json, os, re, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ReportTruncatedError(ValueError):
    pass

_BLOCKING_GAP_MARKERS=(
    '자동 포트폴리오 매매 제외',
    '종목 정체성 불일치','기업 정체성 불일치','공시 종목과 분석 대상 불일치',
    '잘못된 티커','상장폐지','거래정지',
    'ticker identity mismatch','wrong ticker','delisted','trading halted',
)

def blocking_data_gaps(gaps):
    """Keep ordinary research limitations visible; block only integrity failures."""
    return [gap for gap in (gaps or []) if isinstance(gap,str) and any(marker in gap.lower() for marker in _BLOCKING_GAP_MARKERS)]

def validate_completion(metadata):
    metadata=metadata or {}
    reason=str(metadata.get('finish_reason') or metadata.get('stop_reason') or '').lower()
    if reason in ('length','max_tokens','max_output_tokens') or metadata.get('status')=='incomplete':
        raise ReportTruncatedError('Report reached the model output limit; increase RESEARCH_MAX_TOKENS and retry')

def configure_https_ca():
    """Avoid curl_cffi CA-file failures when the virtualenv path is non-ASCII."""
    if any(os.getenv(key) for key in ('SSL_CERT_FILE','CURL_CA_BUNDLE','REQUESTS_CA_BUNDLE')):
        return
    try:
        import certifi
        bundled=str(certifi.where())
    except ImportError:
        return
    if bundled.isascii():
        return
    candidates=[]
    if os.name=='nt':
        for root in (os.getenv('ProgramFiles'),os.getenv('ProgramFiles(x86)')):
            if root:candidates.append(Path(root)/'Git/mingw64/etc/ssl/certs/ca-bundle.crt')
    for candidate in candidates:
        if candidate.is_file() and str(candidate).isascii():
            os.environ['SSL_CERT_FILE']=str(candidate)
            return

def _build_default_graph(config,analysts):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    return TradingAgentsGraph(selected_analysts=analysts,debug=False,config=config)

def _market_unavailable_report(ticker):
    return f'''# 시장 데이터 확인 불가

{ticker}의 검증 가능한 가격·거래량 데이터를 시장 데이터 공급자에서 확인하지 못했습니다. 이 실행에서는 가격과 기술 지표를 추정하지 않고 시장 분석을 생략했습니다. 뉴스, 기업 재무, 13F 공시와 위험 검토는 계속 진행되며, 가격 근거의 부재는 최종 판단의 데이터 누락 항목으로 다뤄야 합니다.'''

def load_env():
    # Small .env loader, no expansion / execution. Environment overrides file.
    path=ROOT/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            key,value=line.split('=',1)
            if re.fullmatch(r'[A-Z][A-Z0-9_]*',key): os.environ.setdefault(key,value.strip().strip('"\''))
    configure_https_ca()

def domain(payload):
    result=subprocess.run([(os.getenv('NODE_BINARY') or 'node'),'--experimental-strip-types',str(ROOT/'scripts/domain-cli.mjs')],input=json.dumps(payload),text=True,capture_output=True,encoding='utf-8',cwd=ROOT,timeout=30)
    if result.returncode: raise ValueError('Invalid fund selection or domain input: '+result.stderr[-800:])
    return json.loads(result.stdout)

def provider_config():
    provider=os.getenv('RESEARCH_PROVIDER')
    deep=os.getenv('RESEARCH_DEEP_MODEL');quick=os.getenv('RESEARCH_QUICK_MODEL')
    if not provider or not deep or not quick: raise RuntimeError('RESEARCH_PROVIDER, RESEARCH_DEEP_MODEL, RESEARCH_QUICK_MODEL must be configured in .env')
    keys={'anthropic':'ANTHROPIC_API_KEY','openai':'OPENAI_API_KEY','google':'GOOGLE_API_KEY','deepseek':'DEEPSEEK_API_KEY','openrouter':'OPENROUTER_API_KEY'}
    if provider in keys and not os.getenv(keys[provider]): raise RuntimeError(f'{keys[provider]} is not configured')
    if provider not in (*keys,'ollama','openai_compatible'): raise RuntimeError('Unsupported research provider')
    if provider in ('ollama','openai_compatible') and not os.getenv('RESEARCH_BACKEND_URL'): raise RuntimeError('RESEARCH_BACKEND_URL is required for a local/custom model')
    max_tokens=int(os.getenv('RESEARCH_MAX_TOKENS','16384'))
    if not 4096<=max_tokens<=65536:raise ValueError('RESEARCH_MAX_TOKENS must be 4096..65536')
    return {'llm_provider':provider,'deep_think_llm':deep,'quick_think_llm':quick,'backend_url':os.getenv('RESEARCH_BACKEND_URL'),'max_debate_rounds':1,'max_risk_discuss_rounds':1,'llm_max_retries':2,'max_tokens':max_tokens,'output_language':'Korean'}

def fingerprint(key,fund_ids):
    config={k:os.getenv(k,'') for k in ('RESEARCH_PROVIDER','RESEARCH_DEEP_MODEL','RESEARCH_QUICK_MODEL','RESEARCH_BACKEND_URL','RESEARCH_MAX_TOKENS')}
    dataset=json.loads((ROOT/'data/filings.json').read_text(encoding='utf-8'))
    selected_data={'period':dataset['period'],'previousPeriod':dataset['previousPeriod'],'funds':sorted([f for f in dataset['funds'] if f['id'] in fund_ids],key=lambda f:f['id'])}
    blob={'key':key,'fundIds':sorted(fund_ids),'dataHash':hashlib.sha256(json.dumps(selected_data,sort_keys=True).encode()).hexdigest(),'date':dt.date.today().isoformat(),'config':config,'schema':11}
    return hashlib.sha256(json.dumps(blob,sort_keys=True).encode()).hexdigest()

def _attach_13f_context(graph,row,fund_ids):
    """Give every TradingAgents decision layer the delayed 13F screening prior."""
    resolver=getattr(graph,'resolve_instrument_context',None)
    if not callable(resolver):return
    buyers=int(row.get('buyers',0));sellers=int(row.get('sellers',0));same=max(buyers,sellers)
    direction='EXPANSION' if buyers>sellers else 'REDUCTION' if sellers>buyers else 'MIXED'
    breadth=round(100*same/len(fund_ids)) if fund_ids else 0
    context=(f"\n13F SCREENING CONTEXT (delayed quarterly evidence, not an order): "
             f"{buyers} selected funds increased or opened the position; {sellers} reduced or closed it. "
             f"The dominant direction is {direction}, supported by {same}/{len(fund_ids)} selected funds ({breadth}%). "
             "Treat this only as a candidate-selection prior, never as the answer, and explicitly decide whether current market, fundamental, news, and risk evidence confirms, weakens, or vetoes it. "
             "Use this five-tier rubric for the final Portfolio Manager rating: Buy only when upside evidence is strong and risk/reward is compelling; "
             "Overweight when bullish evidence has a clear but moderate edge; Hold only when bullish and bearish evidence remain genuinely balanced after all available evidence is weighed; "
             "Underweight when downside, overvaluation, or risk has a clear edge; Sell only when downside evidence is strong or the investment thesis is materially broken. "
             "Uncertainty by itself is not a reason to choose Hold, and the account's current position size must not influence the research rating.")
    graph.resolve_instrument_context=lambda company_name,asset_type='stock':resolver(company_name,asset_type)+context

def load_cached_research(key,fund_ids,context=None):
    """Return a complete report only when every cache-defining input still matches."""
    context=context or domain({'action':'candidates','fundIds':fund_ids})
    path=ROOT/'work/research'/(fingerprint(key,fund_ids)+'.json')
    if not path.exists():return None
    try:result=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError):return None
    valid=(result.get('status')=='completed' and result.get('key')==key and
           result.get('period')==context.get('period') and
           sorted(result.get('fundIds',[]))==sorted(fund_ids) and
           isinstance(result.get('reports'),dict) and
           all(result['reports'].get(name) for name in ('market_report','sentiment_report','news_report','fundamentals_report','final_trade_decision')) and
           result.get('decisionSource')=='tradingagents' and isinstance(result.get('decision'),dict))
    return {**result,'cacheHit':True,'blockingDataGaps':blocking_data_gaps(result.get('decision',{}).get('dataGaps'))} if valid else None

def normalize_tradingagents_decision(raw_signal,final_report,source_urls,market_unavailable=False):
    """Expose the one TradingAgents rating in the legacy decision shape, without another LLM call."""
    rating=str(raw_signal or '').strip().lower()
    mapping={'buy':('buy',100),'overweight':('buy',80),'hold':('watch',50),'underweight':('avoid',80),'sell':('avoid',100)}
    gaps=[]
    if rating not in mapping:
        stance,score='watch',0
        gaps.append('TradingAgents 최종 등급을 해석할 수 없음: 자동 포트폴리오 매매 제외')
    else:stance,score=mapping[rating]
    if market_unavailable:gaps.append('검증 가능한 현재 가격·거래량 데이터 없음: 자동 포트폴리오 매매 제외')
    summary=re.search(r'\*\*Executive Summary\*\*:\s*(.*?)(?:\n\n|$)',final_report,re.S|re.I)
    thesis=summary.group(1).strip() if summary else final_report.strip()
    return {'rating':str(raw_signal),'stance':stance,'score':score,'thesis':thesis,'risks':[],'dataGaps':gaps,'evidenceUrls':source_urls}

def run_research(key,fund_ids,graph_factory=None,on_progress=None):
    from .progress import Progress,attach_progress
    progress=Progress(on_progress);progress.start('context')
    config=provider_config()
    context=domain({'action':'candidates','fundIds':fund_ids})
    row=next((r for r in context['rows'] if r['key']==key),None)
    if not row: raise ValueError('Research requires an equity with at least two selected funds increasing or two decreasing shares')
    today=dt.date.today()
    if (today-dt.date.fromisoformat(context['period'])).days>180: raise ValueError('Filing snapshot is stale; collect the latest quarter')
    cached=load_cached_research(key,fund_ids,context)
    if cached:return cached
    default_graph=graph_factory is None
    if default_graph:
        try:
            from tradingagents.default_config import DEFAULT_CONFIG
        except ImportError as exc: raise RuntimeError('Install pipeline/requirements-ai.txt first') from exc
        config={**DEFAULT_CONFIG.copy(),**{k:v for k,v in config.items() if v not in (None,'')},'results_dir':str(ROOT/'work/tradingagents'),'data_cache_dir':str(ROOT/'work/market-cache'),'memory_log_path':str(ROOT/'work/tradingagents/trading_memory.md')}
        graph=_build_default_graph(config,('market','social','news','fundamentals'))
    else: graph=graph_factory(config)
    _attach_13f_context(graph,row,fund_ids)
    if hasattr(graph,'propagator'):attach_progress(graph,progress)
    progress.complete('context');progress.start('market')
    # Public TradingAgents API. The ticker/date are validated; no funds' text is executable.
    market_report_override=None
    try: state,raw_signal=graph.propagate(row['ticker'],today.isoformat())
    except Exception as exc:
        if not default_graph:
            raise
        from tradingagents.dataflows.errors import NoMarketDataError
        if not isinstance(exc,NoMarketDataError):
            raise
        # Some 13F securities have no usable Yahoo ticker or price history.
        # Price absence must not discard the independent filing/news/fundamental review.
        market_report_override=_market_unavailable_report(row['ticker'])
        progress.complete('market');progress.start('social')
        graph=_build_default_graph(config,('social','news','fundamentals'))
        _attach_13f_context(graph,row,fund_ids)
        if hasattr(graph,'propagator'):attach_progress(graph,progress)
        state,raw_signal=graph.propagate(row['ticker'],today.isoformat())
    report_keys=('market_report','sentiment_report','news_report','fundamentals_report','investment_plan','trader_investment_plan','final_trade_decision')
    reports={k:str(state.get(k,'')) for k in report_keys if state.get(k)}
    if market_report_override:reports['market_report']=market_report_override
    if not all(reports.get(k) for k in ('market_report','sentiment_report','news_report','fundamentals_report','final_trade_decision')): raise ValueError('Analyst reports incomplete; no portfolio decision')
    progress.start('synthesis')
    source_urls=sorted(set([f['sourceUrl'] for f in row['funds']]+[f['previousSourceUrl'] for f in row['funds']]+re.findall(r'https://[^\s<>\]\)"\']+', '\n'.join(reports.values()))))
    progress.complete('synthesis');progress.start('validation')
    decision=normalize_tradingagents_decision(raw_signal,reports['final_trade_decision'],source_urls,bool(market_report_override))
    result={'status':'completed','ticker':row['ticker'],'key':key,'period':context['period'],'fundIds':sorted(fund_ids),'createdAt':dt.datetime.now(dt.timezone.utc).isoformat(),'upstreamSignal':str(raw_signal),'decisionSource':'tradingagents','engine':'TradingAgents','models':{k:config[k] for k in ('llm_provider','deep_think_llm','quick_think_llm')},'decision':decision,'blockingDataGaps':blocking_data_gaps(decision['dataGaps']),'reports':reports,'hedgeContext':row,'sources':source_urls,'brokerConnected':False,'cacheHit':False}
    path=ROOT/'work/research';path.mkdir(parents=True,exist_ok=True)
    output=path/(fingerprint(key,fund_ids)+'.json');temp=output.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(output)
    progress.complete('validation')
    return result
