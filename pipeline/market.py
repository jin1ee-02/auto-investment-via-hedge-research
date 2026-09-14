"""Bounded, cached daily-bar evidence. No LLM calls or brokerage actions."""
import datetime as dt
import json
import math
import re
import threading
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
LOCK=threading.Lock()
MAX_CACHE_AGE=4*3600

def metrics(bars,benchmark,as_of):
    """Daily adjusted closes; omit today's still potentially incomplete session."""
    clean=[b for b in bars if b['date']<as_of and all(isinstance(b.get(k),(int,float)) and math.isfinite(b[k]) and b[k]>0 for k in ('close','volume'))]
    clean=sorted({b['date']:b for b in clean}.values(),key=lambda b:b['date'])
    if len(clean)<50:raise ValueError('At least 50 complete daily bars required')
    last=clean[-1];closes=[b['close'] for b in clean]
    base=clean[-21];ret=last['close']/base['close']-1
    spy={b['date']:b['close'] for b in benchmark if isinstance(b.get('close'),(int,float)) and math.isfinite(b['close']) and b['close']>0}
    relative=None
    if last['date'] in spy and base['date'] in spy:relative=ret-(spy[last['date']]/spy[base['date']]-1)
    return {'asOf':last['date'],'close':round(last['close'],4),'sma20':round(sum(closes[-20:])/20,4),'sma50':round(sum(closes[-50:])/50,4),'return20':ret,'relativeReturn20':relative,'relativeVolume':last['volume']/(sum(b['volume'] for b in clean[-21:-1])/20),'history':[{'date':b['date'],'close':round(b['close'],4)} for b in clean[-60:]]}

def load_bars(ticker,now=None,fetcher=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^]{0,14}',ticker):raise ValueError('Invalid ticker')
    cache=ROOT/'work/daily-market';cache.mkdir(parents=True,exist_ok=True)
    path=cache/(ticker+'.json')
    with LOCK:
        if path.exists():
            data=json.loads(path.read_text(encoding='utf-8'))
            age=(now-dt.datetime.fromisoformat(data['fetchedAt'])).total_seconds()
            if 0<=age<MAX_CACHE_AGE:return data
        if fetcher:
            bars,currency=fetcher(ticker)
        else:
            import yfinance as yf
            stock=yf.Ticker(ticker)
            frame=stock.history(period='6mo',interval='1d',auto_adjust=True,actions=False,timeout=12,raise_errors=True)
            currency=stock.history_metadata.get('currency')
            bars=[{'date':index.date().isoformat(),'close':float(row['Close']),'volume':float(row['Volume'])} for index,row in frame.iterrows()]
        if not bars:raise ValueError('No market data')
        data={'ticker':ticker,'bars':bars,'currency':currency,'fetchedAt':now.isoformat()}
        # Exclude invalid provider values before persisting standards-compliant JSON.
        data['bars']=[b for b in bars if math.isfinite(b['close']) and math.isfinite(b['volume'])]
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,allow_nan=False),encoding='utf-8');temp.replace(path)
        return data

def market_snapshot(ticker,benchmark=None,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    today=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    source='https://finance.yahoo.com/quote/'+ticker+'/history/'
    try:
        data=load_bars(ticker,now)
        result=metrics(data['bars'],benchmark or [],today)
        age=(dt.date.fromisoformat(today)-dt.date.fromisoformat(result['asOf'])).days
        gaps=[]
        if age>5:gaps.append('마지막 가격이 5일 이상 오래되었습니다.')
        if data['currency']!='USD':gaps.append('USD 가격인지 확인되지 않았습니다.')
        if result['relativeReturn20'] is None:gaps.append('같은 날짜의 SPY 비교 데이터가 없습니다.')
        return {'status':'ready' if not gaps else 'limited','ticker':ticker,'currency':data['currency'],'fetchedAt':data['fetchedAt'],'sourceUrl':source,'dataGaps':gaps,**result}
    except Exception as exc:
        return {'status':'unavailable','ticker':ticker,'sourceUrl':source,'dataGaps':['시장 데이터를 가져오지 못했습니다. 잠시 후 다시 확인하세요.'],'errorType':type(exc).__name__}

def market_batch(keys,fund_ids):
    from .research import domain
    context=domain({'action':'candidates','fundIds':fund_ids})
    eligible={r['key']:r for r in context['rows']}
    if not isinstance(keys,list) or not 1<=len(keys)<=8 or any(not isinstance(k,str) or k not in eligible for k in keys) or len(set(keys))!=len(keys):raise ValueError('Select 1..8 eligible unique research candidates')
    try:benchmark=load_bars('SPY')['bars']
    except Exception:benchmark=[]
    rows=[{'key':key,**market_snapshot(eligible[key]['ticker'],benchmark)} for key in keys]
    return {'period':context['period'],'rows':rows,'llmCalls':0,'basis':'adjusted_daily_completed_sessions','benchmark':'SPY'}
