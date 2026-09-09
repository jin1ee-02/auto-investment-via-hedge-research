"""Daily polling / quarterly paper allocation. Manual opt-in; no OS schedule installed."""
import argparse,datetime as dt,json,time
from .research import ROOT,load_env
from .portfolio import quarterly_once

def main():
    load_env();parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');parser.add_argument('--no-refresh',action='store_true');parser.add_argument('--config',default=str(ROOT/'pipeline/strategy.json'));args=parser.parse_args()
    config=json.load(open(args.config,encoding='utf-8'))
    while True:
        try:
            plan=quarterly_once(config,not args.no_refresh)
            print(json.dumps({'status':'completed','period':plan['period'],'planId':plan['id'],'executed':False}),flush=True)
        except Exception as exc:
            print(json.dumps({'status':'blocked','reason':str(exc),'executed':False}),flush=True)
            if not args.watch:raise SystemExit(1)
        if not args.watch:break
        # Restart-safe SQLite deduplication. Missing filings are retried the next day.
        time.sleep(86400)

if __name__=='__main__':main()
