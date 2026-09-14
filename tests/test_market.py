import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline import market

class MarketTests(unittest.TestCase):
    def bars(self):
        return [{'date':(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat(),'close':100+i,'volume':1000} for i in range(61)]
    def test_completed_dates_and_matched_benchmark(self):
        bars=self.bars()
        result=market.metrics(bars,bars,bars[-1]['date'])
        self.assertEqual(result['asOf'],bars[-2]['date'])
        self.assertEqual(result['relativeReturn20'],0)
        self.assertEqual(result['relativeVolume'],1)
        self.assertEqual(result['sma20'],149.5)
        self.assertIsNone(market.metrics(bars,[],bars[-1]['date'])['relativeReturn20'])
        with self.assertRaises(ValueError):market.metrics(bars[:20],[],bars[-1]['date'])
    def test_cache_reuse_and_expiry(self):
        calls=[]
        def fetch(ticker):
            calls.append(ticker)
            return self.bars(),'USD'
        now=dt.datetime(2026,9,12,tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as root,patch.object(market,'ROOT',Path(root)):
            market.load_bars('TEST',now,fetch)
            market.load_bars('TEST',now+dt.timedelta(hours=1),fetch)
            self.assertEqual(len(calls),1)
            market.load_bars('TEST',now+dt.timedelta(hours=5),fetch)
            self.assertEqual(len(calls),2)
            with self.assertRaises(ValueError):market.load_bars('../secret',now,fetch)
    def test_failure_is_explicit(self):
        with patch.object(market,'load_bars',side_effect=RuntimeError('sensitive provider text')):
            result=market.market_snapshot('TEST')
            self.assertEqual(result['status'],'unavailable')
            self.assertNotIn('sensitive',str(result))
