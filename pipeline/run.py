"""Hourly polling / one research and execution batch per filing quarter."""
import argparse,datetime as dt,json,time
from .research import ROOT,load_env
from .portfolio import quarterly_once

def main():
    load_env();parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');parser.add_argument('--no-refresh',action='store_true');parser.add_argument('--config',default=str(ROOT/'pipeline/strategy.json'))
    parser.add_argument('--broker',choices=('none','toss'),default='none');parser.add_argument('--live',action='store_true');parser.add_argument('--reconcile',action='store_true');args=parser.parse_args()
    if (args.live or args.reconcile) and args.broker!='toss':parser.error('--live/--reconcile requires --broker toss')
    broker=None
    if args.broker=='toss':
        from .toss import TossBroker
        broker=TossBroker()
    while True:
        try:
            if args.reconcile:
                from .execution import reconcile
                result=reconcile(broker)
            else:
                config=json.load(open(args.config,encoding='utf-8'))
                plan=quarterly_once(config,not args.no_refresh)
                result={'status':'research_completed','period':plan['period'],'planId':plan['id'],'executed':False}
                if broker:
                    from .execution import execute_once
                    result=execute_once(plan,broker,plan['strategyConfig'],live=args.live)
            print(json.dumps(result),flush=True)
        except Exception as exc:
            print(json.dumps({'status':'blocked','errorType':type(exc).__name__,'reason':str(exc) if isinstance(exc,ValueError) else 'Check local settings and durable ledger; no automatic order retry'}),flush=True)
            if not args.watch:raise SystemExit(1)
        if not args.watch:break
        # Restart-safe SQLite deduplication. Missing filings are retried the next day.
        time.sleep(3600)

if __name__=='__main__':main()
