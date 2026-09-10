import unittest
from pipeline.progress import Progress,attach_progress,STEPS

class ProgressTests(unittest.TestCase):
    def test_service_retains_last_progress_on_failure(self):
        from unittest.mock import patch
        from pipeline.service import worker
        saved=[]
        def fail(key,ids,on_progress):
            on_progress({'current':'news','completed':2,'total':9,'percent':22})
            raise RuntimeError('private provider details')
        with patch('pipeline.service.save_job',side_effect=lambda _,value:saved.append(value)),patch('pipeline.service.run_research',side_effect=fail):worker('id','key',['fund'])
        self.assertEqual(saved[-1]['status'],'failed')
        self.assertEqual(saved[-1]['progress']['current'],'news')
        self.assertNotIn('private provider',str(saved))
    def test_tool_round_does_not_finish_analyst_or_publish_content(self):
        events=[];p=Progress(events.append)
        p.node_start('Market Analyst','first');p.node_end({'messages':['private prompt']},'first')
        self.assertEqual(events[-1]['completed'],0)
        p.node_start('Market Analyst','second');p.node_end({'market_report':'private report'},'second')
        self.assertEqual(events[-1]['completed'],1)
        p.node_start('Market Analyst','third');p.node_end({'market_report':'another report'},'third')
        self.assertEqual(events[-1]['completed'],1)
        self.assertNotIn('private',str(events))
    def test_failed_stage_does_not_reach_100(self):
        events=[];p=Progress(events.append)
        for key,_ in STEPS[:-1]:p.complete(key)
        p.start('validation');self.assertLess(events[-1]['percent'],100)
        p.complete('validation');self.assertEqual(events[-1]['percent'],100)
    def test_real_langgraph_callback_wiring_without_llm(self):
        try:
            from langgraph.graph import StateGraph,START,END
        except ImportError:self.skipTest('Optional AI dependencies not installed')
        from typing import TypedDict
        from types import SimpleNamespace
        class State(TypedDict):market_report:str
        workflow=StateGraph(State)
        workflow.add_node('Market Analyst',lambda state:{'market_report':'report'})
        workflow.add_edge(START,'Market Analyst');workflow.add_edge('Market Analyst',END)
        graph=SimpleNamespace(propagator=SimpleNamespace(get_graph_args=lambda callbacks=None:{'config':{'callbacks':callbacks}}))
        events=[];attach_progress(graph,Progress(events.append))
        workflow.compile().invoke({'market_report':''},**graph.propagator.get_graph_args())
        self.assertEqual(events[-1]['completed'],1)
        self.assertEqual(events[-1]['current'],'market')
