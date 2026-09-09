"""A hard execution boundary. This module has no HTTP implementation or secrets."""
from typing import Protocol

class Broker(Protocol):
    def submit_orders(self, orders:list[dict])->dict: ...

class TossBrokerDisabled:
    def submit_orders(self,orders:list[dict])->dict:
        raise RuntimeError('Toss execution is intentionally unavailable. No API connection or verification has been implemented.')

class PaperBroker:
    def submit_orders(self,orders:list[dict])->dict:
        # Not a fill simulator: merely records a dry-run intent.
        return {'status':'dry_run','executed':False,'orders':orders,'fills':[]}
