import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline import execution, portfolio


CONFIG = {'fundIds':['a'], 'budgetUsd':1000, 'maxWeight':.5, 'minCash':.1,
          'maxHoldings':8, 'startPeriod':'2026-01-01', 'maxTurnover':.3,
          'minTradeUsd':10, 'feeBuffer':.01}


def plan():
    return {'id':'test', 'period':'2026-06-30',
            'createdAt':dt.datetime.now(dt.timezone.utc).isoformat(),
            'portfolio':{'positions':[{'ticker':'AAPL','amount':500}]},
            'research':[{'ticker':'AAPL', 'upstreamSignal':'Buy',
                         'decision':{'stance':'buy','confidence':.8,'dataGaps':[]}}]}


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


class ExecutionTests(unittest.TestCase):
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
    def test_same_quarter_restart_config_and_plan_changes_never_resubmit(self):
        b=Broker();first=execution.execute_once(plan(),b,CONFIG,True)
        changed=plan();changed['id']='new';changed['createdAt']='2000-01-01T00:00:00+00:00'
        again=execution.execute_once(changed,b,{**CONFIG,'budgetUsd':9000},True)
        self.assertEqual(first,again);self.assertEqual(len(b.sent),1)
    def test_unknown_response_not_retried_even_in_next_quarter(self):
        b=Broker();b.fail=True
        result=execution.execute_once(plan(),b,CONFIG,True)
        self.assertEqual(result['status'],'needs_reconciliation')
        execution.execute_once(plan(),b,CONFIG,True)
        new=plan();new['period']='2026-09-30'
        with self.assertRaisesRegex(ValueError,'reconciliation'):execution.execute_once(new,b,CONFIG,True)
        self.assertEqual(len(b.sent),1)
    def test_crash_after_intent_commit_never_resubmits(self):
        b=Broker()
        with patch.object(b,'submit',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):execution.execute_once(plan(),b,CONFIG,True)
        result=execution.execute_once(plan(),b,CONFIG,True)
        self.assertEqual(result['status'],'submitting');self.assertEqual(b.sent,[])
    def test_dry_run_does_not_consume_live_quarter(self):
        b=Broker();execution.execute_once(plan(),b,CONFIG)
        self.assertEqual(b.sent,[])
        execution.execute_once(plan(),b,CONFIG,True);self.assertEqual(len(b.sent),1)
    def test_unknown_holdings_preserved_and_no_sale_proceeds_spent(self):
        b=Broker();b.cash='0';b.holdings=[{'symbol':'AAPL','currency':'USD','marketCountry':'US','quantity':'10'}, {'symbol':'MSFT','currency':'USD','marketCountry':'US','quantity':'5'}]
        p=plan();p['research'][0].update(upstreamSignal='Sell');p['research'][0]['decision']['stance']='avoid'
        orders=execution.draft_orders(p,b,CONFIG)
        self.assertEqual([(o['symbol'],o['side']) for o in orders],[('AAPL','SELL')])
    def test_disagreement_and_gaps_hold(self):
        for signal,gaps in [('Hold',[]),('Buy',['missing news'])]:
            p=plan();p['research'][0]['upstreamSignal']=signal;p['research'][0]['decision']['dataGaps']=gaps
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
        b=Broker();execution.execute_once(plan(),b,CONFIG,True)
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
            self.assertEqual(json.loads(requests[1].data),order)
    def test_live_switch_blocks_transport(self):
        from pipeline.toss import TossBroker
        with patch.dict('os.environ',{'TOSS_CLIENT_ID':'test','TOSS_CLIENT_SECRET':'test','TOSS_ACCOUNT_SEQ':'1','TOSS_ENABLE_LIVE':'false'}):
            broker=TossBroker()
            with patch.object(broker.opener,'open') as network:
                with self.assertRaises(RuntimeError):broker.submit({})
                network.assert_not_called()


if __name__=='__main__':unittest.main()
