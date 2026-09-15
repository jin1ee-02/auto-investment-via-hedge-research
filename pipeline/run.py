"""User-triggered research, account proposal, and explicit terminal approval."""
import argparse,json,sys,uuid
from .research import ROOT,load_env
from .portfolio import build_plan,build_account_plan,select_candidates

def main():
    load_env();parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');parser.add_argument('--no-refresh',action='store_true');parser.add_argument('--config',default=str(ROOT/'pipeline/strategy.json'))
    parser.add_argument('--broker',choices=('none','toss'),default='none');parser.add_argument('--live',action='store_true');parser.add_argument('--reconcile',action='store_true')
    parser.add_argument('--approve',metavar='REPORT_ID');parser.add_argument('--reject',metavar='REPORT_ID');args=parser.parse_args()
    if args.live:parser.error('Unattended --live is disabled. Generate a report, then use --broker toss --approve REPORT_ID')
    if args.watch:parser.error('Quarterly unattended trading was removed; start the pipeline on demand')
    if sum(bool(v) for v in (args.approve,args.reject,args.reconcile))>1:parser.error('Choose only one approval/rejection/reconciliation action')
    if (args.approve or args.reject) and args.watch:parser.error('Approval cannot run in watch mode')
    if args.approve and args.broker!='toss':parser.error('--approve requires --broker toss')
    if (args.live or args.reconcile) and args.broker!='toss':parser.error('--live/--reconcile requires --broker toss')
    broker=None
    if args.broker=='toss':
        from .toss import TossBroker
        broker=TossBroker()
    if args.approve or args.reject:
        from .approval import get_review,decide_review
        review_id=args.approve or args.reject
        review=get_review(review_id)
        if args.reject:
            decide_review(review_id,'',reject=True);print('Review rejected. No orders sent.');return
        if not sys.stdin.isatty():parser.error('Approval requires an interactive owner terminal')
        print(json.dumps({'account':review['account'],'period':review['plan']['period'],'expiresAt':review['expiresAt'],'orders':review['orders'],'research':review['plan'].get('research',[])},ensure_ascii=False,indent=2))
        phrase=input(f'실제 주문을 승인하려면 APPROVE {review_id} 를 입력하세요. 그 외 입력은 취소: ')
        if phrase!='APPROVE '+review_id:
            print('승인을 취소했습니다. 주문은 전송하지 않았습니다.');return
        decide_review(review_id,phrase)
        from .execution import execute_once
        result=execute_once(review['plan'],broker,review['config'],live=True,approval_id=review_id)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    try:
        if args.reconcile:
            from .execution import reconcile
            result=reconcile(broker)
        else:
            config=json.load(open(args.config,encoding='utf-8'));ids=config['fundIds'];candidate_filter=config.get('candidateFilter');candidate_count=config.get('researchCandidateCount',6);run_id=uuid.uuid4().hex
            if broker:
                if type(candidate_count) is not int or not 1<=candidate_count<=8:raise ValueError('researchCandidateCount must be 1..8')
                _,candidates=select_candidates(ids,candidate_count,candidate_filter);candidates=candidates[:candidate_count]
                if not candidates:raise ValueError('No eligible research candidates')
                from .research import run_research
                reports=[run_research(candidate['key'],ids) for candidate in candidates]
                plan=build_account_plan(ids,candidates,reports,broker,config,run_id)
                from .execution import draft_orders
                orders=draft_orders(plan,broker,plan['strategyConfig']);plan['orders']=orders
                if orders:
                    plan.update(proposalStatus='ready',executionReady=True)
                    from .approval import prepare_review
                    review=prepare_review(plan,broker,plan['strategyConfig'],orders)
                    result={'status':'awaiting_approval','runId':run_id,'planId':plan['id'],'executed':False,'reviewId':review['id'],'expiresAt':review['expiresAt'],'report':str(ROOT/'work/approvals'/(review['id']+'.html')),'message':'Review the report and explicitly approve in an interactive terminal. No orders sent.'}
                else:
                    plan.update(proposalStatus='no_orders',executionReady=False)
                    result={'status':'no_orders','runId':run_id,'planId':plan['id'],'executed':False,'message':'Research and account allocation completed; no eligible orders were produced.'}
            else:
                plan=build_plan(ids,count=candidate_count,run_missing=True,candidate_filter=candidate_filter)
                result={'status':'research_completed','runId':run_id,'period':plan['period'],'planId':plan['id'],'executed':False}
        print(json.dumps(result),flush=True)
    except Exception as exc:
        print(json.dumps({'status':'blocked','errorType':type(exc).__name__,'reason':str(exc) if isinstance(exc,ValueError) else 'Check local settings and durable ledger; no automatic order retry'}),flush=True);raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False));raise SystemExit(1)
    except (EOFError,KeyboardInterrupt):
        print('실행을 중단했습니다. 전송 중이었다면 주문 원장을 확인하세요.');raise SystemExit(1)
