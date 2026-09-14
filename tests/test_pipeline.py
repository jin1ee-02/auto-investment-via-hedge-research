import json,unittest,tempfile,datetime as dt
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from pipeline.collect import parse_table,resolve_ticker
from pipeline.research import validate_decision,run_research,fingerprint
from pipeline.broker import TossBrokerDisabled,PaperBroker
from pipeline import portfolio

XML='''<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">{rows}</informationTable>'''
def row(kind='',value=100,shares=10):return f'<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>{"<putCall>"+kind+"</putCall>" if kind else ""}</infoTable>'
class Tests(unittest.TestCase):
    def test_cache_ignores_collection_timestamp_and_unselected_funds(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.research.ROOT',Path(tmp)):
            path=Path(tmp)/'data';path.mkdir();file=path/'filings.json'
            data={'period':'2026-06-30','previousPeriod':'2026-03-31','generatedAt':'first','funds':[{'id':'a','snapshots':[]},{'id':'b','snapshots':[]}]}
            file.write_text(json.dumps(data));first=fingerprint('A',['a'])
            data['generatedAt']='second';data['funds'][1]['snapshots']=[{'changed':True}];file.write_text(json.dumps(data))
            self.assertEqual(first,fingerprint('A',['a']))
            data['funds'][0]['snapshots']=[{'changed':True}];file.write_text(json.dumps(data))
            self.assertNotEqual(first,fingerprint('A',['a']))
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
    def test_schema_and_citations(self):
        for key,value in [('score',float('nan')),('confidence',2),('stance','strong_buy'),('evidenceUrls',['https://invented.example'])]:
            d=self.decision();d[key]=value
            with self.assertRaises(ValueError):validate_decision(d,['https://www.sec.gov/test'])
    def test_research_orchestration_with_provider_double(self):
        # Explicit test double; never shipped or displayed as a real AI report.
        today=dt.date.today();p=(today.replace(day=1)-dt.timedelta(days=1)).isoformat();d=self.decision()
        class Graph:
            deep_thinking_llm=SimpleNamespace(invoke=lambda _:SimpleNamespace(content=json.dumps(d)))
            def propagate(self,ticker,date):
                self.asserted=(ticker,date)
                return {'market_report':'Verified market report','sentiment_report':'Sentiment report','news_report':'News report','fundamentals_report':'Financial report','final_trade_decision':'Buy'},'Buy'
        context={'period':p,'rows':[{'key':'APPLE:EQUITY','ticker':'AAPL','funds':[{'sourceUrl':'https://www.sec.gov/test','previousSourceUrl':'https://www.sec.gov/test'}]}]}
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.research.ROOT',Path(tmp)),patch('pipeline.research.provider_config',return_value={'llm_provider':'test','deep_think_llm':'test','quick_think_llm':'test'}),patch('pipeline.research.domain',return_value=context),patch('pipeline.research.fingerprint',return_value='a'*64):
            result=run_research('APPLE:EQUITY',['fund'],lambda _:Graph());self.assertEqual(result['decision']['score'],75);self.assertFalse(result['brokerConnected']);self.assertTrue((Path(tmp)/'work/research'/('a'*64+'.json')).exists())
            def unexpected(_): raise AssertionError('Cached result must not call TradingAgents again')
            self.assertEqual(run_research('APPLE:EQUITY',['fund'],unexpected),result)
    def test_incomplete_reports_fail_closed(self):
        graph=SimpleNamespace(propagate=lambda *_:({'market_report':'Only market'},'BUY'))
        context={'period':dt.date.today().isoformat(),'rows':[{'key':'A','ticker':'AAPL','funds':[]}]}
        with patch('pipeline.research.provider_config',return_value={}),patch('pipeline.research.domain',return_value=context),patch('pipeline.research.fingerprint',return_value='test-incomplete'):
            with self.assertRaisesRegex(ValueError,'incomplete'):run_research('A',['f'],lambda _:graph)
    def test_missing_research_does_not_create_plan(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.portfolio.ROOT',Path(tmp)),patch('pipeline.portfolio.select_candidates',return_value=({'period':'2026-06-30'},[{'key':'A','ticker':'AAPL'}])),patch('pipeline.portfolio.fingerprint',return_value='a'*64):
            with self.assertRaisesRegex(ValueError,'required first'):portfolio.build_plan(['f'])
if __name__=='__main__':unittest.main()
