import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline import execution,approval
from test_execution import Broker,CONFIG,plan


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        p=patch('pipeline.execution.ROOT',self.root);p.start();self.addCleanup(p.stop)
        p=patch.dict('os.environ',{'TOSS_ENABLE_LIVE':'true'});p.start();self.addCleanup(p.stop)
        self.broker=Broker();self.plan=plan()

    def prepare(self):return approval.prepare_review(self.plan,self.broker,CONFIG)
    def approve(self,r):return approval.decide_review(r['id'],'APPROVE '+r['id'])
    def execute(self,r):return execution.execute_once(self.plan,self.broker,CONFIG,True,approval_id=r['id'])

    def test_live_switch_alone_cannot_submit(self):
        with self.assertRaisesRegex(ValueError,'approval'):execution.execute_once(self.plan,self.broker,CONFIG,True)
        self.assertEqual(self.broker.sent,[])

    def test_pending_or_wrong_phrase_cannot_submit(self):
        r=self.prepare()
        with self.assertRaisesRegex(ValueError,'approval'):self.execute(r)
        with self.assertRaisesRegex(ValueError,'phrase'):approval.decide_review(r['id'],'yes')
        self.assertEqual(self.broker.sent,[])

    def test_owner_approval_is_consumed_and_restart_never_resubmits(self):
        r=self.prepare();self.approve(r);self.execute(r);self.execute(r)
        self.assertEqual(len(self.broker.sent),1)
        self.assertEqual(approval.get_review(r['id'])['status'],'consumed')

    def test_account_settings_research_and_order_changes_require_new_review(self):
        for change in ('account','config','plan','orders'):
            with self.subTest(change=change):
                r=self.prepare();self.approve(r)
                broker=Broker();p=json.loads(json.dumps(self.plan));config=dict(CONFIG)
                if change=='account':broker.account='different'
                if change=='config':config['minTradeUsd']=11
                if change=='plan':p['research'][0]['decision']['dataGaps']=['new missing evidence']
                if change=='orders':broker.cash='200'
                with self.assertRaisesRegex(ValueError,'changed'):execution.execute_once(p,broker,config,True,approval_id=r['id'])
                self.assertEqual(broker.sent,[])

    def test_expired_approval_rejected(self):
        r=self.prepare();self.approve(r)
        with execution.ledger() as db:
            saved=approval.get_review(r['id']);saved['expiresAt']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1)).isoformat()
            db.execute('UPDATE reviews SET payload=? WHERE id=?',(json.dumps(saved),r['id']))
        with self.assertRaisesRegex(ValueError,'expired'):self.execute(r)
        self.assertEqual(self.broker.sent,[])

    def test_rejection_and_tampered_file_do_not_approve(self):
        r=self.prepare();approval.decide_review(r['id'],'',reject=True)
        file=self.root/'work/approvals'/(r['id']+'.json')
        data=json.loads(file.read_text(encoding='utf-8'));data['status']='approved';file.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'approval'):self.execute(r)
        self.assertEqual(self.broker.sent,[])

    def test_identical_poll_reuses_pending_report(self):
        first=self.prepare();second=self.prepare()
        self.assertEqual(first['id'],second['id'])
        self.assertTrue((self.root/'work/approvals'/(first['id']+'.html')).exists())

    def test_unattended_cli_live_flag_is_blocked(self):
        from pipeline.run import main
        with patch('pipeline.run.load_env'),patch('sys.argv',['run','--broker','toss','--live','--watch']),patch('sys.stderr'):
            with self.assertRaises(SystemExit):main()
        self.assertEqual(self.broker.sent,[])

    def test_piped_approval_is_blocked_without_consuming_review(self):
        from pipeline.run import main
        r=self.prepare()
        with patch('pipeline.run.load_env'),patch('pipeline.toss.TossBroker',return_value=self.broker),patch('sys.argv',['run','--broker','toss','--approve',r['id']]),patch('sys.stdin.isatty',return_value=False),patch('sys.stderr'):
            with self.assertRaises(SystemExit):main()
        self.assertEqual(approval.get_review(r['id'])['status'],'pending')
        self.assertEqual(self.broker.sent,[])


if __name__=='__main__':unittest.main()
