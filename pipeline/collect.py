"""SEC 13F collector. Standard library only; cached, serial, < 4 requests/sec.
Never treats a missing filing/table as an empty portfolio. No HedgeFollow scraping.
"""
import argparse, datetime as dt, hashlib, json, os, re, statistics, time, urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work' / 'sec-cache'
NS = {'f': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}
SECURITY_METADATA = json.loads((ROOT/'data/security-metadata.json').read_text(encoding='utf-8'))
CUSIP_TICKERS = SECURITY_METADATA['tickers']
ABBREVIATIONS = {
    'AMER':'AMERICA','AMERN':'AMERICAN','ASSOC':'ASSOCIATES','BANC':'BANK','BK':'BANK',
    'CMNTYS':'COMMUNITIES','CTZNS':'CITIZENS','ELEC':'ELECTRIC','ENTMT':'ENTERTAINMENT',
    'FINL':'FINANCIAL','HLDG':'HOLDINGS','HLDGS':'HOLDINGS','INDS':'INDUSTRIES',
    'INTL':'INTERNATIONAL','INVT':'INVESTMENT','INVTS':'INVESTMENTS','MATLS':'MATERIALS',
    'MFR':'MANUFACTURING','MNG':'MINING','MKT':'MARKET','MKTS':'MARKETS','MTRS':'MOTORS',
    'NATL':'NATIONAL','PAC':'PACIFIC','PETE':'PETROLEUM','PPTY':'PROPERTY',
    'PPTYS':'PROPERTIES','RES':'RESOURCES','RLTY':'REALTY','SVCS':'SERVICES',
    'SYS':'SYSTEMS','TECH':'TECHNOLOGY','TELECOM':'TELECOMMUNICATIONS'
}
NAME_STOP_WORDS = {'INC','INCORPORATED','CORP','CORPORATION','CO','COMPANY','COS','LTD','LIMITED','PLC','LLC','LP','THE','OF','NEW','DEL','DE','NV','SA','AG','SWITZ','GROUP','IN','I'}

def request(url, user_agent):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / hashlib.sha256(url.encode()).hexdigest()
    if path.exists() and time.time()-path.stat().st_mtime < 21600:
        return path.read_bytes()
    if not user_agent or '@' not in user_agent:
        raise ValueError('SEC_USER_AGENT must contain an identifying contact email')
    time.sleep(.3)
    req = urllib.request.Request(url, headers={'User-Agent': user_agent, 'Accept-Encoding':'identity'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read(25_000_000)
            path.write_bytes(raw)
            return raw
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2: raise
            time.sleep(2 ** (attempt+1))

def jget(url, ua): return json.loads(request(url, ua))
def text(element, name):
    found=element.find('.//f:'+name, NS)
    return found.text.strip() if found is not None and found.text else ''

def parse_table(raw, filing_date):
    root=ET.fromstring(raw)
    rows=root.findall('.//f:infoTable',NS)
    if not rows: raise ValueError('No 13F informationTable rows; refusing empty snapshot')
    multiplier=1 if filing_date >= '2023-01-03' else 1000
    result={}
    for row in rows:
        cusip=text(row,'cusip'); kind=text(row,'putCall').upper() or ('EQUITY' if text(row,'sshPrnamtType')=='SH' else 'PRINCIPAL')
        cls=text(row,'titleOfClass')
        # Separate share classes, options and principal amounts. Sum manager-discretion rows.
        key=f'{cusip}:{kind}'
        value=float(text(row,'value'))*multiplier; shares=float(text(row,'sshPrnamt'))
        if not cusip or value < 0 or shares < 0: raise ValueError('Invalid 13F row')
        if key not in result:
            result[key]={'key':key,'cusip':cusip,'name':text(row,'nameOfIssuer'),'class':cls,'kind':kind,'value':0,'shares':0,'ticker':None}
        result[key]['value']+=value; result[key]['shares']+=shares
    return list(result.values())

def normalize(name):
    tokens=re.sub(r'[^A-Z0-9]+',' ',name.upper().replace('&',' AND ')).split()
    return ''.join(ABBREVIATIONS.get(token,token) for token in tokens if token not in NAME_STOP_WORDS)

def ticker_map_from_rows(raw):
    result={}
    for row in raw.values(): result.setdefault(normalize(row['title']),[]).append(row)
    return result

def ticker_map(ua):
    return ticker_map_from_rows(jget('https://www.sec.gov/files/company_tickers.json',ua))

def select_common_ticker(entries):
    candidates=sorted({entry['ticker'] for entry in entries if re.fullmatch(r'[A-Z]{1,5}',entry['ticker'])},key=lambda ticker:(len(ticker),ticker))
    return candidates[0] if candidates and (len(candidates)==1 or len(candidates[0])<len(candidates[1])) else None

def resolve_ticker(row, tickers):
    curated=CUSIP_TICKERS.get(row.get('cusip',''))
    if curated:
        row['ticker']=curated
        return
    # Reject preferreds, notes, warrants and rights before matching common equity.
    if not re.search(r'\b(COM|COMMON|ORD|ORDINARY|NAMEN|CL [ABC]|CAP STK|SHS|SH BEN INT|ADS|ADR)\b',row['class'].upper()) or re.search(r'\b(PFD|PREF|NOTE|WARRANT|W EXP|RIGHT)\b',row['class'].upper()):
        return
    normalized=normalize(row['name']);entries=tickers.get(normalized,[])
    if not entries and len(normalized)>=8:
        matches=[value for key,value in tickers.items() if min(len(key),len(normalized))>=8 and min(len(key),len(normalized))/max(len(key),len(normalized))>=.72 and (key.startswith(normalized) or normalized.startswith(key))]
        if len(matches)==1: entries=matches[0]
    if normalized=='ALPHABET':
        wanted='GOOGL' if 'CL A' in row['class'] or 'CAP STK CL A' in row['class'] else 'GOOG' if 'CL C' in row['class'] else None
        match=next((r for r in entries if r['ticker']==wanted),None)
        if match: row['ticker']=match['ticker']; row['issuerCik']=str(match['cik_str'])
        return
    ticker=entries[0]['ticker'] if len(entries)==1 else select_common_ticker(entries)
    if ticker:
        row['ticker']=ticker
        match=next(entry for entry in entries if entry['ticker']==ticker)
        row['issuerCik']=str(match['cik_str'])

def get_filing(fund, record, ua, tickers):
    acc=record['accessionNumber']; date=record['filingDate']; report=record['reportDate']
    base=f'https://www.sec.gov/Archives/edgar/data/{int(fund["cik"])}/{acc.replace("-", "")}'
    files=jget(base+'/index.json',ua)['directory']['item']
    table=None; source=None
    for item in files:
        name=item['name']
        if not name.lower().endswith('.xml') or name.lower()=='primary_doc.xml': continue
        raw=request(base+'/'+name,ua)
        if b'informationTable' in raw:
            if table is not None: raise ValueError('Multiple information tables require manual review')
            table=parse_table(raw,date); source=base+'/'+name
    if table is None: raise ValueError('13F table not found')
    for row in table: resolve_ticker(row,tickers)
    primary=ET.fromstring(request(base+'/primary_doc.xml',ua))
    declared=next((float(n.text) for n in primary.iter() if n.tag.split('}')[-1]=='tableValueTotal'),None)
    total=sum(r['value'] for r in table)
    if declared is not None and abs(declared*(1 if date>='2023-01-03' else 1000)-total)>max(1,len(table)):
        raise ValueError('Declared table total does not reconcile')
    return {'period':report,'filedAt':date,'accession':acc,'sourceUrl':source,'totalValue':total,'positions':table,'complete':True}

def collect(ua, period=None, only=None):
    today=dt.date.today()
    start=dt.date(today.year, 3*((today.month-1)//3)+1, 1)
    latest=period or (start-dt.timedelta(days=1)).isoformat()
    d=dt.date.fromisoformat(latest); prev=(dt.date(d.year, d.month-2,1)-dt.timedelta(days=1)).isoformat()
    funds=json.loads((ROOT/'pipeline/funds.json').read_text(encoding='utf-8'))
    tickers=ticker_map(ua); output=[]
    for fund in funds:
        if only and fund['id'] not in only: continue
        fund={**fund,'snapshots':[], 'status':'pending'}
        try:
            submissions=jget(f'https://data.sec.gov/submissions/CIK{int(fund["cik"]):010d}.json',ua)
            fund['secName']=submissions['name']
            if normalize(fund['name']).replace('MANAGEMENT','').replace('ASSOCIATES','')[:6] not in normalize(submissions['name']):
                raise ValueError('Configured fund name does not match SEC CIK identity')
            recent=submissions['filings']['recent']
            records=[{k:recent[k][i] for k in ('form','reportDate','filingDate','accessionNumber')} for i in range(len(recent['form']))]
            for p in (prev, latest):
                matches=[r for r in records if r['form'] in ('13F-HR','13F-HR/A') and r['reportDate']==p]
                if not matches: raise ValueError(f'{p}: matching 13F not yet available')
                filing=max(matches,key=lambda x:(x['filingDate'],x['accessionNumber']))
                if filing['form']=='13F-HR/A':
                    base=f'https://www.sec.gov/Archives/edgar/data/{int(fund["cik"])}/{filing["accessionNumber"].replace("-", "")}'
                    primary=ET.fromstring(request(base+'/primary_doc.xml',ua))
                    amendment=next((n.text.strip().upper() for n in primary.iter() if n.tag.split('}')[-1]=='amendmentType'),'')
                    if amendment!='RESTATEMENT':raise ValueError(f'{p}: additive amendment requires reconciliation; excluded')
                fund['snapshots'].append(get_filing(fund,filing,ua,tickers))
                fund['snapshots'][-1]['amendmentMode']='restatement' if filing['form']=='13F-HR/A' else 'original'
            fund['status']='ready'
            for snapshot in fund['snapshots']:
                implied=[p['value']/p['shares'] for p in snapshot['positions'] if p['kind']=='EQUITY' and p['ticker'] and p['shares']>0]
                if len(implied)>5 and statistics.median(implied)<1:
                    raise ValueError('단위 검토 필요: 공시 평가단가 중앙값이 $1 미만입니다. 원문 단위 오류 가능성으로 통합 분석 제외')
            print(f'{fund["name"]}: {len(fund["snapshots"][-1]["positions"])} positions',flush=True)
        except Exception as exc:
            fund['status']='unavailable';fund['error']=str(exc)
            print(f'{fund["name"]}: unavailable: {exc}',flush=True)
        output.append(fund)
    dataset={'schemaVersion':1,'generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'period':latest,'previousPeriod':prev,'source':'SEC EDGAR','universeStatus':'popular_20_verified_2026_09_09_plus_3_supplementary','funds':output}
    path=ROOT/'data'/'filings.json';path.parent.mkdir(exist_ok=True)
    if not any(f['status']=='ready' for f in output): raise RuntimeError('No complete fund pair; keeping existing dataset')
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(dataset,ensure_ascii=False),encoding='utf-8');temp.replace(path)
    (ROOT/'public/filings.json').write_text(json.dumps(dataset,ensure_ascii=False),encoding='utf-8')
    defaults=set(json.loads((ROOT/'pipeline/strategy.json').read_text(encoding='utf-8'))['fundIds'])
    bootstrap={**dataset,'funds':[{**f,'status':f['status'] if f['id'] in defaults or f['status']!='ready' else 'loading','snapshots':[s if f['id'] in defaults else {**s,'positions':[],'complete':False} for s in f['snapshots']]} for f in output]}
    (ROOT/'data/bootstrap.json').write_text(json.dumps(bootstrap,ensure_ascii=False),encoding='utf-8')
    return dataset

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--period');parser.add_argument('--fund',action='append');parser.add_argument('--user-agent',default=os.getenv('SEC_USER_AGENT'))
    args=parser.parse_args();collect(args.user_agent,args.period,args.fund)
