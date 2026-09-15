import json,unittest,tempfile,datetime as dt
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from pipeline.collect import parse_table,resolve_ticker
from pipeline.research import run_research,fingerprint,configure_https_ca,load_cached_research,blocking_data_gaps,normalize_tradingagents_decision
from pipeline.broker import TossBrokerDisabled,PaperBroker
from pipeline import portfolio

XML='''<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">{rows}</informationTable>'''
def row(kind='',value=100,shares=10):return f'<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>{"<putCall>"+kind+"</putCall>" if kind else ""}</infoTable>'
class Tests(unittest.TestCase):
    def test_truncated_provider_responses_rejected(self):
        from pipeline.research import validate_completion,ReportTruncatedError
        for metadata in ({'finish_reason':'length'},{'finish_reason':'MAX_TOKENS'},{'stop_reason':'max_tokens'},{'status':'incomplete'}):
            with self.assertRaises(ReportTruncatedError):validate_completion(metadata)
        validate_completion({'finish_reason':'stop'})

    def test_only_critical_integrity_gaps_block_orders(self):
        ordinary=['13F는 현재 보유를 보여주지 않음','최신 공식 재무제표 원문 재확인 필요','향후 금리 경로 불확실']
        self.assertEqual(blocking_data_gaps(ordinary),[])
        critical='검증 가능한 현재 가격·거래량 데이터 없음: 자동 포트폴리오 매매 제외'
        self.assertEqual(blocking_data_gaps([*ordinary,critical]),[critical])

    def test_research_is_bounded_by_candidate_limit(self):
        candidates=[{'key':str(i),'ticker':'T'+str(i),'buyers':2,'sellers':0} for i in range(10)]
        reports=[{'key':c['key'],'ticker':c['ticker'],'status':'completed','period':'2026-06-30','fundIds':['f'],'upstreamSignal':'Buy','decision':self.decision()} for c in candidates]
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.select_candidates',return_value=({'period':'2026-06-30'},candidates)) as select,patch('pipeline.portfolio.fingerprint',side_effect=lambda key,ids:key),patch('pipeline.portfolio.run_research',side_effect=reports) as research,patch('pipeline.portfolio.domain',return_value={'positions':[]}) as allocate:
            result=portfolio.build_plan(['f'],count=2,run_missing=True)
            select.assert_called_once_with(['f'],2,None)
            self.assertEqual(research.call_count,2)
            self.assertEqual(len(result['research']),2)
            self.assertEqual(len(allocate.call_args.args[0]['scores']),2)
            self.assertEqual(allocate.call_args.args[0]['count'],2)

    def test_non_ascii_certifi_path_uses_ascii_git_ca_bundle(self):
        import os
        env=dict(os.environ)
        env.pop('SSL_CERT_FILE',None);env.pop('CURL_CA_BUNDLE',None);env.pop('REQUESTS_CA_BUNDLE',None)
        env['ProgramFiles']=r'C:\Program Files';env.pop('ProgramFiles(x86)',None)
        with patch.dict(os.environ,env,clear=True),patch('certifi.where',return_value=r'C:\사용자\cacert.pem'),patch.object(Path,'is_file',return_value=True):
            configure_https_ca()
            self.assertEqual(os.environ['SSL_CERT_FILE'],r'C:\Program Files\Git\mingw64\etc\ssl\certs\ca-bundle.crt')
    def test_cache_ignores_collection_timestamp_and_unselected_funds(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.research.ROOT',Path(tmp)):
            path=Path(tmp)/'data';path.mkdir();file=path/'filings.json'
            data={'period':'2026-06-30','previousPeriod':'2026-03-31','generatedAt':'first','funds':[{'id':'a','snapshots':[]},{'id':'b','snapshots':[]}]}
            file.write_text(json.dumps(data));first=fingerprint('A',['a'])
            data['generatedAt']='second';data['funds'][1]['snapshots']=[{'changed':True}];file.write_text(json.dumps(data))
            self.assertEqual(first,fingerprint('A',['a']))
            data['funds'][0]['snapshots']=[{'changed':True}];file.write_text(json.dumps(data))
            self.assertNotEqual(first,fingerprint('A',['a']))
    def test_complete_cache_is_reused_for_every_matching_symbol(self):
        context={'period':'2026-06-30'}
        required={name:name for name in ('market_report','sentiment_report','news_report','fundamentals_report','final_trade_decision')}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.research.ROOT',Path(tmp)),patch('pipeline.research.fingerprint',side_effect=lambda key,_:{'A':'a'*64,'B':'b'*64}[key]):
            folder=Path(tmp)/'work/research';folder.mkdir(parents=True)
            for key in ('A','B'):
                (folder/((key.lower()*64)+'.json')).write_text(json.dumps({'status':'completed','key':key,'period':'2026-06-30','fundIds':['f1','f2'],'reports':required,'decisionSource':'tradingagents','decision':{'stance':'buy','dataGaps':[]}}))
            self.assertTrue(load_cached_research('A',['f2','f1'],context)['cacheHit'])
            self.assertTrue(load_cached_research('B',['f1','f2'],context)['cacheHit'])
    def test_grouping_and_options(self):
        result=parse_table(XML.format(rows=row()+row()+row('Put')).encode(),'2026-08-14')
        self.assertEqual(len(result),2);self.assertEqual(result[0]['value'],200);self.assertEqual(result[0]['shares'],20);self.assertEqual(result[1]['kind'],'PUT')
    def test_units_and_empty_rejected(self):
        self.assertEqual(parse_table(XML.format(rows=row()).encode(),'2022-01-01')[0]['value'],100000)
        with self.assertRaises(ValueError):parse_table(b'<html>Blocked</html>','2026-01-01')
    def test_warrants_not_mapped_to_common(self):
        r={'name':'APPLE INC','class':'W EXP 2028','ticker':None};resolve_ticker(r,{'APPLE':[{'ticker':'AAPL','cik_str':320193}]});self.assertIsNone(r['ticker'])
    def test_curated_cusip_and_abbreviated_name_resolve(self):
        curated={'cusip':'060505104','name':'BANK OF AMER CORP','class':'COM','ticker':None};resolve_ticker(curated,{})
        self.assertEqual(curated['ticker'],'BAC')
        abbreviated={'cusip':'test','name':'APPLIED MATLS INC','class':'COM','ticker':None};resolve_ticker(abbreviated,{'APPLIEDMATERIALS':[{'ticker':'AMAT','cik_str':6951}]})
        self.assertEqual(abbreviated['ticker'],'AMAT')
    def test_no_toss_network_path(self):
        with self.assertRaises(RuntimeError):TossBrokerDisabled().submit_orders([{'ticker':'AAPL'}])
        self.assertFalse(PaperBroker().submit_orders([])['executed'])
    def decision(self):return {'score':75,'confidence':.8,'stance':'buy','thesis':'Test evidence','risks':['valuation'],'dataGaps':[],'evidenceUrls':['https://www.sec.gov/test']}
    def test_tradingagents_rating_is_normalized_without_an_extra_ai_opinion(self):
        expected={'Buy':('buy',100),'Overweight':('buy',80),'Hold':('watch',50),'Underweight':('avoid',80),'Sell':('avoid',100)}
        for rating,(stance,score) in expected.items():
            result=normalize_tradingagents_decision(rating,f'**Executive Summary**: {rating} summary',[])
            self.assertEqual((result['stance'],result['score']),(stance,score))
    def test_research_orchestration_with_provider_double(self):
        today=dt.date.today();p=(today.replace(day=1)-dt.timedelta(days=1)).isoformat()
        class Graph:
            deep_thinking_llm=SimpleNamespace(invoke=lambda *_:(_ for _ in ()).throw(AssertionError('No second AI synthesis call is allowed')))
            def propagate(self,ticker,date):
                self.asserted=(ticker,date)
                return {'market_report':'Verified market report','sentiment_report':'Sentiment report','news_report':'News report','fundamentals_report':'Financial report','final_trade_decision':'Buy'},'Buy'
        context={'period':p,'rows':[{'key':'APPLE:EQUITY','ticker':'AAPL','funds':[{'sourceUrl':'https://www.sec.gov/test','previousSourceUrl':'https://www.sec.gov/test'}]}]}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.research.ROOT',Path(tmp)),patch('pipeline.research.provider_config',return_value={'llm_provider':'test','deep_think_llm':'test','quick_think_llm':'test'}),patch('pipeline.research.domain',return_value=context),patch('pipeline.research.fingerprint',return_value='a'*64):
            result=run_research('APPLE:EQUITY',['fund'],lambda _:Graph());self.assertEqual(result['decision']['score'],100);self.assertEqual(result['decisionSource'],'tradingagents');self.assertFalse(result['brokerConnected']);self.assertFalse(result['cacheHit']);self.assertTrue((Path(tmp)/'work/research'/('a'*64+'.json')).exists())
            def unexpected(_): raise AssertionError('Cached result must not call TradingAgents again')
            cached=run_research('APPLE:EQUITY',['fund'],unexpected);self.assertTrue(cached['cacheHit']);self.assertEqual(cached['createdAt'],result['createdAt'])
    def test_incomplete_reports_fail_closed(self):
        graph=SimpleNamespace(propagate=lambda *_:({'market_report':'Only market'},'BUY'))
        context={'period':dt.date.today().isoformat(),'rows':[{'key':'A','ticker':'AAPL','funds':[]}]}
        with patch('pipeline.research.provider_config',return_value={}),patch('pipeline.research.domain',return_value=context),patch('pipeline.research.fingerprint',return_value='test-incomplete'):
            with self.assertRaisesRegex(ValueError,'incomplete'):run_research('A',['f'],lambda _:graph)
    def test_missing_market_data_falls_back_to_non_price_research(self):
        from tradingagents.dataflows.errors import NoMarketDataError
        decision=self.decision();created=[]
        class MissingMarket:
            def propagate(self,*_):raise NoMarketDataError('TEST','TEST','no rows')
        class Fallback:
            deep_thinking_llm=SimpleNamespace(invoke=lambda _:SimpleNamespace(content=json.dumps(decision)))
            def propagate(self,*_):return {'sentiment_report':'Sentiment','news_report':'News','fundamentals_report':'Fundamentals','final_trade_decision':'Hold'},'Hold'
        def build(_,analysts):
            created.append(analysts)
            return MissingMarket() if len(created)==1 else Fallback()
        context={'period':dt.date.today().isoformat(),'rows':[{'key':'TEST:EQUITY','ticker':'TEST','funds':[{'sourceUrl':'https://www.sec.gov/test','previousSourceUrl':'https://www.sec.gov/test'}]}]}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.research.ROOT',Path(tmp)),patch('pipeline.research.provider_config',return_value={'llm_provider':'test','deep_think_llm':'test','quick_think_llm':'test'}),patch('pipeline.research.domain',return_value=context),patch('pipeline.research.fingerprint',return_value='b'*64),patch('pipeline.research._build_default_graph',side_effect=build):
            result=run_research('TEST:EQUITY',['fund'])
        self.assertEqual(created,[('market','social','news','fundamentals'),('social','news','fundamentals')])
        self.assertIn('시장 데이터 확인 불가',result['reports']['market_report'])
        self.assertTrue(result['decision']['dataGaps'])
        self.assertEqual(result['status'],'completed')
    def test_missing_research_does_not_create_plan(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.select_candidates',return_value=({'period':'2026-06-30'},[{'key':'A','ticker':'AAPL'}])),patch('pipeline.portfolio.fingerprint',return_value='a'*64):
            with self.assertRaisesRegex(ValueError,'required first'):portfolio.build_plan(['f'])
    def test_account_plan_uses_only_us_assets_and_tradingagents_strength(self):
        class AccountBroker:
            account='1'
            def get(self,path,**query):
                if path=='holdings':return {'items':[{'symbol':'AAPL','marketCountry':'US','currency':'USD','quantity':'2','lastPrice':'100','marketValue':{'amount':'200'}},{'symbol':'MSFT','marketCountry':'US','currency':'USD','quantity':'1','lastPrice':'100','marketValue':{'amount':'100'}},{'symbol':'005930','marketCountry':'KR','currency':'KRW','quantity':'3','lastPrice':'70000','marketValue':{'amount':'210000'}}]}
                if path=='buying-power':return {'currency':'USD','cashBuyingPower':'700'}
                raise AssertionError((path,query))
        candidate={'key':'APPLE:EQUITY','ticker':'AAPL','buyers':2,'sellers':0,'holders':2}
        report={'status':'completed','key':candidate['key'],'ticker':'AAPL','period':'2026-06-30','fundIds':['a','b'],'upstreamSignal':'Buy','decision':self.decision()}
        config={'fundIds':['a','b'],'maxWeight':.2,'minCash':.1,'maxHoldings':8,'maxTurnover':.3,'minTradeUsd':10,'feeBuffer':.01,'candidateFilter':{'direction':'all','minFunds':2,'includeMixed':True}}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.fingerprint',return_value='hash'):
            result=portfolio.build_account_plan(['a','b'],[candidate],[report],AccountBroker(),config,'run')
        self.assertEqual(result['accountSnapshot']['usCapitalUsd'],'1000')
        self.assertEqual(result['accountSnapshot']['excludedKrHoldingCount'],1)
        self.assertEqual(result['accountSnapshot']['protectedHoldingsValue'],'100')
        self.assertEqual(result['research'][0]['action'],'buy')
        self.assertEqual(result['research'][0]['allocationScore'],100.0)
        self.assertNotIn('minConfidence',result['constraints'])
        self.assertLessEqual(result['portfolio']['positions'][0]['weight'],.2)
    def test_hold_remains_no_trade_for_expansion_consensus(self):
        class Broker:
            account='1'
            def get(self,path,**query):
                if path=='holdings':return {'items':[]}
                if path=='buying-power':return {'currency':'USD','cashBuyingPower':'1000'}
                raise AssertionError(path)
        candidate={'key':'A:EQUITY','ticker':'A','buyers':2,'sellers':0,'holders':2}
        report={'status':'completed','key':'A:EQUITY','ticker':'A','period':'2026-06-30','fundIds':['a','b'],'upstreamSignal':'Hold','decision':self.decision()}
        config={'fundIds':['a','b'],'maxWeight':.2,'minCash':.1,'maxHoldings':8,'maxTurnover':.3,'minTradeUsd':10,'feeBuffer':.01}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.fingerprint',return_value='hash'):
            result=portfolio.build_account_plan(['a','b'],[candidate],[report],Broker(),config,'run')
        self.assertEqual(result['research'][0]['action'],'hold')
        self.assertEqual(result['research'][0]['allocationScore'],0)
        self.assertEqual(result['portfolio']['positions'],[])
    def test_overweight_is_an_actionable_buy_with_reduced_strength(self):
        class Broker:
            account='1'
            def get(self,path,**query):
                if path=='holdings':return {'items':[]}
                if path=='buying-power':return {'currency':'USD','cashBuyingPower':'1000'}
                raise AssertionError(path)
        candidate={'key':'A:EQUITY','ticker':'A','buyers':2,'sellers':0,'holders':2}
        report={'status':'completed','key':'A:EQUITY','ticker':'A','period':'2026-06-30','fundIds':['a','b'],'upstreamSignal':'Overweight','decision':self.decision()}
        config={'fundIds':['a','b'],'maxWeight':.2,'minCash':.1,'maxHoldings':8,'maxTurnover':.3,'minTradeUsd':10,'feeBuffer':.01}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.fingerprint',return_value='hash'):
            result=portfolio.build_account_plan(['a','b'],[candidate],[report],Broker(),config,'run')
        self.assertEqual(result['research'][0]['action'],'buy')
        self.assertEqual(result['research'][0]['allocationScore'],80.0)
    def test_ordinary_data_gap_is_a_warning_not_an_order_gate(self):
        class Broker:
            account='1'
            def get(self,path,**query):
                if path=='holdings':return {'items':[]}
                if path=='buying-power':return {'currency':'USD','cashBuyingPower':'1000'}
                raise AssertionError(path)
        candidate={'key':'A:EQUITY','ticker':'A','buyers':2,'sellers':0,'holders':2}
        report={'status':'completed','key':'A:EQUITY','ticker':'A','period':'2026-06-30','fundIds':['a','b'],'upstreamSignal':'Buy','decision':{**self.decision(),'dataGaps':['missing news']}}
        config={'fundIds':['a','b'],'maxWeight':.2,'minCash':.1,'maxHoldings':8,'maxTurnover':.3,'minTradeUsd':10,'feeBuffer':.01}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.fingerprint',return_value='hash'):
            result=portfolio.build_account_plan(['a','b'],[candidate],[report],Broker(),config,'run')
        self.assertEqual(result['research'][0]['action'],'buy')
        self.assertEqual(len(result['portfolio']['positions']),1)
        self.assertEqual(result['research'][0]['blockingDataGaps'],[])
        self.assertEqual(result['research'][0]['limitations'],['missing news'])
    def test_existing_overweight_holding_blocks_new_opening_without_forced_sale(self):
        class Broker:
            account='1'
            def get(self,path,**query):
                if path=='holdings':return {'items':[{'symbol':'OLD','marketCountry':'US','currency':'USD','quantity':'8','marketValue':{'amount':'800'}}]}
                if path=='buying-power':return {'currency':'USD','cashBuyingPower':'200'}
                raise AssertionError(path)
        candidates=[{'key':'OLD:EQUITY','ticker':'OLD','buyers':2,'sellers':0,'holders':2},{'key':'NEW:EQUITY','ticker':'NEW','buyers':2,'sellers':0,'holders':2}]
        reports=[{'status':'completed','key':c['key'],'ticker':c['ticker'],'period':'2026-06-30','fundIds':['a','b'],'upstreamSignal':'Buy','decision':self.decision()} for c in candidates]
        config={'fundIds':['a','b'],'maxWeight':.2,'minCash':.1,'maxHoldings':8,'maxTurnover':.3,'minTradeUsd':10,'feeBuffer':.01}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.fingerprint',return_value='hash'):
            result=portfolio.build_account_plan(['a','b'],candidates,reports,Broker(),config,'run')
        self.assertEqual(result['portfolio']['positions'][0]['ticker'],'OLD')
        self.assertEqual(result['portfolio']['positions'][0]['amount'],800.0)
        self.assertNotIn('NEW',[position['ticker'] for position in result['portfolio']['positions']])
if __name__=='__main__':unittest.main()
