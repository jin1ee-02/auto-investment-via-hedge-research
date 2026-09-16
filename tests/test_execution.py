import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline import execution, portfolio, approval


CONFIG = {'fundIds':['a'], 'budgetUsd':1000, 'maxWeight':.5, 'minCash':.1,
          'maxHoldings':8, 'startPeriod':'2026-01-01', 'maxTurnover':.3,
          'minTradeUsd':10, 'feeBuffer':.01}


def plan():
    return {'id':'test', 'period':'2026-06-30',
            'createdAt':dt.datetime.now(dt.timezone.utc).isoformat(),
            'portfolio':{'positions':[{'ticker':'AAPL','amount':500}]},
            'research':[{'ticker':'AAPL', 'upstreamSignal':'Buy',
                         'decision':{'stance':'buy','score':70,'confidence':.8,'dataGaps':[]}}]}


class Broker:
    account = '1'
    def __init__(self):
        self.sent=[]; self.cash='1000'; self.holdings=[]; self.open=[]; self.fail=False
    def get(self, path, **query):
        if path=='orders':return {'orders':self.open}
        if path=='holdings':return {'items':self.holdings}
        if path=='buying-power':return {'currency':'USD','cashBuyingPower':self.cash}
        if path=='prices':return [{'symbol':s,'lastPrice':'100','currency':'USD','timestamp':dt.datetime.now(dt.timezone.utc).isoformat()} for s in query['symbols'].split(',')]
        if path=='sellable-quantity':return {'sellableQuantity':'10'}
        if path.startswith('orders/'):return {'status':'PARTIAL_FILLED','execution':{'filledQuantity':'1'}}
        raise AssertionError(path)
    def submit(self, request):
        self.sent.append(request)
        if self.fail:raise TimeoutError('Simulated lost response after broker accepts order')
        return {'orderId':'accepted'}


def approved_execution(p,b,config):
    # Only test brokers: simulates the human approval step using a durable review.
    if not hasattr(b,'review_id'):
        review=approval.prepare_review(p,b,config)
        approval.decide_review(review['id'],'APPROVE '+review['id'])
        b.review_id=review['id']
    return execution.execute_once(p,b,config,True,approval_id=b.review_id)


class ExecutionTests(unittest.TestCase):
    def test_relaxed_sizing_uses_cash_without_reserve_and_keeps_fee_buffer(self):
        config={**CONFIG,'maxWeight':1,'minCash':0,'maxTurnover':1,'minTradeUsd':0}
        p=plan();p['portfolio']['positions'][0]['amount']=1000
        b=Broker()
        orders=execution.draft_orders(p,b,config)
        self.assertEqual(orders[0]['quantity'],'9')
        self.assertEqual(b.sent,[])
        targets=portfolio._allocate_account_targets([{'ticker':'AAPL','allocationScore':100}],1000,0,set(),config)
        self.assertEqual(targets[0]['amount'],1000)

    def test_zero_minimum_allows_small_order_but_negative_is_rejected(self):
        config={**CONFIG,'maxWeight':1,'minCash':0,'maxTurnover':1,'minTradeUsd':0}
        b=Broker();original=b.get
        def get(path,**query):
            rows=original(path,**query)
            if path=='prices':
                for row in rows:row['lastPrice']='50'
            return rows
        b.get=get
        p=plan();p['portfolio']['positions'][0]['amount']=50
        self.assertEqual(execution.draft_orders(p,b,config)[0]['quantity'],'1')
        with self.assertRaises(ValueError):execution.validate_config({**config,'minTradeUsd':-1})

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        p=patch('pipeline.execution.ROOT',self.root);p.start();self.addCleanup(p.stop)
        p=patch.dict('os.environ',{'TOSS_ENABLE_LIVE':'true'});p.start();self.addCleanup(p.stop)
    def test_quantity_turnover_and_wire_schema(self):
        orders=execution.draft_orders(plan(),Broker(),CONFIG)
        self.assertEqual(orders[0]['quantity'],'3')
        self.assertEqual(orders[0]['price'],'100.00')
        self.assertLessEqual(len(orders[0]['clientOrderId']),36)
    def test_legacy_confidence_field_is_ignored(self):
        p=plan();p['research'][0]['decision']['confidence']=.01
        self.assertEqual(execution.draft_orders(p,Broker(),CONFIG)[0]['side'],'BUY')
    def test_same_quarter_restart_config_and_plan_changes_never_resubmit(self):
        b=Broker();first=approved_execution(plan(),b,CONFIG)
        changed=plan();changed['id']='new';changed['createdAt']='2000-01-01T00:00:00+00:00'
        again=approved_execution(changed,b,{**CONFIG,'budgetUsd':9000})
        self.assertEqual(first,again);self.assertEqual(len(b.sent),1)
    def test_distinct_batches_can_execute_in_the_same_filing_quarter(self):
        b=Broker();first=plan();first['batchId']='batch-one';approved_execution(first,b,CONFIG)
        del b.review_id
        second=plan();second['batchId']='batch-two';approved_execution(second,b,CONFIG)
        self.assertEqual(len(b.sent),2)
    def test_unknown_response_not_retried_even_in_next_quarter(self):
        b=Broker();b.fail=True
        result=approved_execution(plan(),b,CONFIG)
        self.assertEqual(result['status'],'needs_reconciliation')
        approved_execution(plan(),b,CONFIG)
        new=plan();new['period']='2026-09-30'
        with self.assertRaisesRegex(ValueError,'reconciliation'):approved_execution(new,b,CONFIG)
        self.assertEqual(len(b.sent),1)
    def test_unresolved_legacy_quarter_batch_blocks_new_batch(self):
        with execution.ledger() as db:
            db.execute('INSERT INTO batches VALUES (?,?,?)',('1','2026-03-31',json.dumps({'status':'needs_reconciliation','orders':[]})))
        b=Broker();p=plan();p['batchId']='new-batch'
        with self.assertRaisesRegex(ValueError,'reconciliation'):approved_execution(p,b,CONFIG)
        self.assertEqual(b.sent,[])
    def test_crash_after_intent_commit_never_resubmits(self):
        b=Broker()
        with patch.object(b,'submit',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):approved_execution(plan(),b,CONFIG)
        result=approved_execution(plan(),b,CONFIG)
        self.assertEqual(result['status'],'submitting');self.assertEqual(b.sent,[])
    def test_dry_run_does_not_consume_live_quarter(self):
        b=Broker();execution.execute_once(plan(),b,CONFIG)
        self.assertEqual(b.sent,[])
        approved_execution(plan(),b,CONFIG);self.assertEqual(len(b.sent),1)
    def test_unknown_holdings_preserved_and_no_sale_proceeds_spent(self):
        b=Broker();b.cash='0';b.holdings=[{'symbol':'AAPL','currency':'USD','marketCountry':'US','quantity':'10'}, {'symbol':'MSFT','currency':'USD','marketCountry':'US','quantity':'5'}]
        p=plan();p['research'][0].update(upstreamSignal='Sell');p['research'][0]['decision']['stance']='avoid'
        orders=execution.draft_orders(p,b,CONFIG)
        self.assertEqual([(o['symbol'],o['side']) for o in orders],[('AAPL','SELL')])
    def test_disagreement_and_gaps_hold(self):
        for signal,gaps in [('Hold',[]),('Buy',['검증 가능한 현재 가격·거래량 데이터 없음: 자동 포트폴리오 매매 제외'])]:
            p=plan();p['research'][0]['upstreamSignal']=signal;p['research'][0]['decision']['dataGaps']=gaps
            self.assertEqual(execution.draft_orders(p,Broker(),CONFIG),[])
    def test_ordinary_research_limitations_do_not_block_orders(self):
        p=plan();p['research'][0]['decision']['dataGaps']=['13F는 현재 보유를 보여주지 않음','뉴스 원문 재확인 필요']
        self.assertEqual(execution.draft_orders(p,Broker(),CONFIG)[0]['side'],'BUY')
    def test_buy_research_never_creates_a_rebalancing_sale(self):
        b=Broker();b.holdings=[{'symbol':'AAPL','currency':'USD','marketCountry':'US','quantity':'10'}]
        self.assertEqual(execution.draft_orders(plan(),b,CONFIG),[])
    def test_underweight_signal_can_sell_only_an_avoid_holding(self):
        b=Broker();b.holdings=[{'symbol':'AAPL','currency':'USD','marketCountry':'US','quantity':'2'}]
        p=plan();p['research'][0].update(upstreamSignal='Underweight');p['research'][0]['decision']['stance']='avoid'
        self.assertEqual(execution.draft_orders(p,b,CONFIG)[0]['side'],'SELL')
    def test_account_plan_never_trades_a_hold_even_if_action_is_incorrect(self):
        p=plan();p['mode']='account_proposal';p['research'][0].update(upstreamSignal='Hold',action='buy',actionReason='13F expansion with neutral TradingAgents');p['portfolio']['positions'][0]['amount']=200
        self.assertEqual(execution.draft_orders(p,Broker(),CONFIG),[])
    def test_existing_orders_and_expired_plan_block(self):
        b=Broker();b.open=[{'symbol':'AAPL'}]
        with self.assertRaisesRegex(ValueError,'Open orders'):execution.draft_orders(plan(),b,CONFIG)
        b.open=[];p=plan();p['createdAt']='2020-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'expired'):execution.draft_orders(p,b,CONFIG)
    def test_cash_reserve_fees_and_stop(self):
        b=Broker();b.cash='200'
        self.assertEqual(execution.draft_orders(plan(),b,CONFIG),[])
        (self.root/'work').mkdir();(self.root/'work/STOP_TRADING').touch()
        with self.assertRaisesRegex(ValueError,'STOP'):execution.execute_once(plan(),b,CONFIG,True)
    def test_reconcile_only_reads_and_preserves_partial_fill(self):
        b=Broker();approved_execution(plan(),b,CONFIG)
        result=execution.reconcile(b)
        self.assertEqual(result[0]['orders'][0]['brokerStatus'],'PARTIAL_FILLED')
        self.assertEqual(len(b.sent),1)
    def test_invalid_numbers(self):
        for value in [float('nan'),-1,True]:
            with self.assertRaises(ValueError):execution.validate_config({**CONFIG,'budgetUsd':value})


class QuarterlyTests(unittest.TestCase):
    def test_same_quarter_research_frozen_across_amendment_and_model_changes(self):
        today=dt.date.today();period=today.replace(month=3*((today.month-1)//3)+1,day=1)-dt.timedelta(days=1)
        prior=period.replace(month=period.month-2,day=1)-dt.timedelta(days=1)
        dataset={'period':period.isoformat(),'previousPeriod':prior.isoformat(),'funds':[{'id':'a','status':'ready','snapshots':[{'period':p.isoformat(),'complete':True,'filedAt':p.isoformat()} for p in (period,prior)]}]}
        result=plan();result['period']=period.isoformat()
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.select_candidates',return_value=({},[{'ticker':'AAPL'}])),patch('pipeline.portfolio.build_plan',return_value=result) as build:
            folder=Path(tmp)/'data';folder.mkdir();file=folder/'filings.json';file.write_text(json.dumps(dataset))
            first=portfolio.quarterly_once(CONFIG,False)
            dataset['amendment']='changed';file.write_text(json.dumps(dataset))
            second=portfolio.quarterly_once({**CONFIG,'budgetUsd':9000},False)
            self.assertEqual(first,second);self.assertEqual(build.call_count,1)


class TransportTests(unittest.TestCase):
    def test_auth_403_explains_toss_allowed_ip_requirement(self):
        import io
        import urllib.error
        from pipeline.toss import TossBroker
        error=urllib.error.HTTPError('https://openapi.tossinvest.com/oauth2/token',403,'Forbidden',{},io.BytesIO(b'{"error":"access_denied"}'))
        with patch.dict('os.environ',{'TOSS_CLIENT_ID':'test','TOSS_CLIENT_SECRET':'test','TOSS_ACCOUNT_SEQ':'1'}),patch('pipeline.toss.time.sleep'):
            broker=TossBroker()
            with patch.object(broker.opener,'open',side_effect=error):
                with self.assertRaisesRegex(RuntimeError,'허용 IP'):
                    broker.get('holdings')

    def test_single_brokerage_account_is_discovered_without_env_sequence(self):
        import io
        from pipeline.toss import TossBroker
        responses=[{'access_token':'test-token','expires_in':3600},{'result':[{'accountNo':'masked','accountSeq':7,'accountType':'BROKERAGE'}]}]
        with patch.dict('os.environ',{'TOSS_CLIENT_ID':'test','TOSS_CLIENT_SECRET':'test','TOSS_ACCOUNT_SEQ':''}),patch('pipeline.toss.time.sleep'),patch('urllib.request.OpenerDirector.open',side_effect=lambda *_args,**_kwargs:io.BytesIO(json.dumps(responses.pop(0)).encode())):
            broker=TossBroker()
        self.assertEqual(broker.account,'7')
    def test_auth_form_and_order_json_against_official_contract(self):
        import io
        from pipeline.toss import TossBroker
        requests=[]
        def respond(request, **kwargs):
            requests.append(request)
            value={'access_token':'test-token','expires_in':3600} if len(requests)==1 else {'result':{'orderId':'server-id'}}
            return io.BytesIO(json.dumps(value).encode())
        with patch.dict('os.environ',{'TOSS_CLIENT_ID':'test-client','TOSS_CLIENT_SECRET':'test-secret','TOSS_ACCOUNT_SEQ':'1','TOSS_ENABLE_LIVE':'true'}),patch('pipeline.toss.time.sleep'):
            broker=TossBroker()
            with patch.object(broker.opener,'open',side_effect=respond):
                order=execution.draft_orders(plan(),Broker(),CONFIG)[0]
                self.assertEqual(broker.submit(order),{'orderId':'server-id'})
            self.assertEqual(requests[0].full_url,'https://openapi.tossinvest.com/oauth2/token')
            self.assertIn(b'grant_type=client_credentials',requests[0].data)
            self.assertEqual(requests[1].full_url,'https://openapi.tossinvest.com/api/v1/orders')
            self.assertEqual(requests[1].get_header('X-tossinvest-account'),'1')
            self.assertEqual(json.loads(requests[1].data),{key:order[key] for key in ('clientOrderId','symbol','side','orderType','timeInForce','quantity','price')})
    def test_live_switch_blocks_transport(self):
        from pipeline.toss import TossBroker
        with patch.dict('os.environ',{'TOSS_CLIENT_ID':'test','TOSS_CLIENT_SECRET':'test','TOSS_ACCOUNT_SEQ':'1','TOSS_ENABLE_LIVE':'false'}):
            broker=TossBroker()
            with patch.object(broker.opener,'open') as network:
                with self.assertRaises(RuntimeError):broker.submit({})
                network.assert_not_called()


if __name__=='__main__':unittest.main()
