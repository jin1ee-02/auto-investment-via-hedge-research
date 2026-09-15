import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline import service


class PipelineServiceTests(unittest.TestCase):
    def test_enqueue_pipeline_uses_requested_candidate_count(self):
        candidates=[{'key':f'K{i}:EQUITY','ticker':f'T{i}','buyers':10-i,'sellers':0,'holders':2} for i in range(10)]
        submitted=[]
        pool=SimpleNamespace(submit=lambda *args:submitted.append(args))
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.service.ROOT',Path(tmp)),patch('pipeline.service.provider_config'),patch('pipeline.service.select_candidates',return_value=({},candidates)),patch('pipeline.service.POOL',pool):
            result=service.enqueue_pipeline(['fund-a','fund-b'],candidate_count=4)
            saved=service.get_job(result['runId'])
        self.assertEqual(result['status'],'queued')
        self.assertEqual(len(result['selectedCandidates']),4)
        self.assertEqual(result['candidateCount'],4)
        self.assertEqual(saved['selectedCandidates'],result['selectedCandidates'])
        self.assertEqual(len(submitted),1)

    def test_enqueue_pipeline_rejects_out_of_range_candidate_count(self):
        with patch('pipeline.service.provider_config'):
            with self.assertRaisesRegex(ValueError,'candidateCount'):
                service.enqueue_pipeline(['fund-a','fund-b'],candidate_count=9)

    def test_transient_research_failure_is_retried(self):
        transient=type('OpenAIConnectionError',(Exception,),{})
        with patch('pipeline.service.run_research',side_effect=[transient('offline'),{'status':'completed'}]) as research,patch('pipeline.service.time.sleep'):
            result=service._run_research_with_retry('key',['fund'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(research.call_count,2)

    def test_enqueue_pipeline_reattaches_to_active_run(self):
        candidates=[{'key':'A:EQUITY','ticker':'A','buyers':2,'sellers':0,'holders':2}]
        submitted=[];pool=SimpleNamespace(submit=lambda *args:submitted.append(args))
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.service.ROOT',Path(tmp)),patch('pipeline.service.provider_config'),patch('pipeline.service.select_candidates',return_value=({},candidates)),patch('pipeline.service.POOL',pool):
            first=service.enqueue_pipeline(['fund-a','fund-b'])
            second=service.enqueue_pipeline(['fund-a','fund-b'])
            active=service.active_pipeline()
        self.assertEqual(second['runId'],first['runId'])
        self.assertTrue(second['resumed'])
        self.assertEqual(active['runId'],first['runId'])
        self.assertEqual(len(submitted),1)


if __name__=='__main__':unittest.main()
