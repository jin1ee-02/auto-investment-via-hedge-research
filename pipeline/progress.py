"""Public progress metadata only; never publishes prompts or internal reasoning."""
import datetime as dt

STEPS=[('context','공시 확인·준비'),('market','시장·기술 분석'),('social','감성 분석'),('news','뉴스 분석'),('fundamentals','재무 분석'),('debate','강세·약세 검토'),('trader','매매안 작성'),('risk','리스크 검토'),('synthesis','펀드 공통 변화 종합'),('validation','결과 검증·저장')]
NODES={'Sentiment Analyst':('social','sentiment_report'),'Social Analyst':('social','sentiment_report'),'Market Analyst':('market','market_report'),'News Analyst':('news','news_report'),'Fundamentals Analyst':('fundamentals','fundamentals_report'),'Bull Researcher':('debate',None),'Bear Researcher':('debate',None),'Research Manager':('debate','investment_plan'),'Trader':('trader','trader_investment_plan'),'Aggressive Analyst':('risk',None),'Conservative Analyst':('risk',None),'Neutral Analyst':('risk',None),'Portfolio Manager':('risk','final_trade_decision')}

class Progress:
    def __init__(self,emit=None):
        self.emit=emit or (lambda _:None);self.done=set();self.current='context';self.started=dt.datetime.now(dt.timezone.utc).isoformat();self.runs={}
    def publish(self):
        self.emit({'current':self.current,'completed':len(self.done),'total':len(STEPS),'percent':round(100*len(self.done)/len(STEPS)),'startedAt':self.started,'updatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'steps':[{'id':key,'label':label,'status':'completed' if key in self.done else 'running' if key==self.current else 'pending'} for key,label in STEPS]})
    def start(self,key):self.current=key;self.publish()
    def complete(self,key):self.done.add(key);self.publish()
    def node_start(self,name,run_id):
        if name in NODES:
            self.runs[run_id]=name;self.start(NODES[name][0])
    def node_end(self,outputs,run_id):
        name=self.runs.pop(run_id,None)
        if name:
            key,field=NODES[name]
            if field and isinstance(outputs,dict) and outputs.get(field):self.complete(key)

def attach_progress(graph,progress):
    from langchain_core.callbacks import BaseCallbackHandler
    class Callback(BaseCallbackHandler):
        def on_chain_start(self,serialized,inputs,*,run_id,**kwargs):
            progress.node_start(kwargs.get('name'),run_id)
        def on_chain_end(self,outputs,*,run_id,**kwargs):progress.node_end(outputs,run_id)
    original=graph.propagator.get_graph_args
    callback=Callback()
    def get_args(callbacks=None):return original(callbacks=[*(callbacks or []),callback])
    graph.propagator.get_graph_args=get_args
