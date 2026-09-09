"""Enrich stored 13F snapshots from local SEC ticker data and curated CUSIP checks."""
import hashlib, json
from pathlib import Path
from pipeline.collect import ROOT, CUSIP_TICKERS, resolve_ticker, ticker_map_from_rows

SEC_TICKERS_URL='https://www.sec.gov/files/company_tickers.json'

def enrich(path:Path,tickers):
    dataset=json.loads(path.read_text(encoding='utf-8'))
    known=dict(CUSIP_TICKERS)
    for fund in dataset['funds']:
        for snapshot in fund.get('snapshots',[]):
            for position in snapshot.get('positions',[]):
                if position.get('ticker'):known[position['cusip']]=position['ticker']
    changed=0
    for fund in dataset['funds']:
        for snapshot in fund.get('snapshots',[]):
            for position in snapshot.get('positions',[]):
                if position.get('ticker'):continue
                ticker=known.get(position['cusip'])
                if ticker:position['ticker']=ticker
                else:resolve_ticker(position,tickers)
                if position.get('ticker'):
                    known[position['cusip']]=position['ticker'];changed+=1
    path.write_text(json.dumps(dataset,ensure_ascii=False),encoding='utf-8')
    return dataset,changed

def main():
    cache=ROOT/'work/sec-cache'/hashlib.sha256(SEC_TICKERS_URL.encode()).hexdigest()
    if not cache.exists():raise RuntimeError('Local SEC company ticker cache is missing')
    tickers=ticker_map_from_rows(json.loads(cache.read_text(encoding='utf-8')))
    bootstrap,bootstrap_changed=enrich(ROOT/'data/bootstrap.json',tickers)
    filings,filings_changed=enrich(ROOT/'data/filings.json',tickers)
    (ROOT/'public/filings.json').write_text(json.dumps(filings,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'bootstrap':bootstrap_changed,'filings':filings_changed,'funds':len(filings['funds'])}))

if __name__=='__main__':main()
