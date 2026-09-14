"""Discover a single brokerage account and save its ID; never sends orders."""
import json
import re
from .research import ROOT, load_env
from .toss import TossBroker, BrokerError


def main():
    load_env()
    try:
        accounts = TossBroker(discover_account=True).get('accounts')
        if not isinstance(accounts, list):
            raise BrokerError('Unexpected account-list format')
        eligible = [a for a in accounts if a.get('accountType') == 'BROKERAGE']
        if len(eligible) != 1:
            print(json.dumps({'status': 'selection_required', 'eligibleAccounts': len(eligible)}))
            return 1
        seq = eligible[0].get('accountSeq')
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
            raise BrokerError('Invalid accountSeq returned')
        path = ROOT / '.env'
        original = path.read_text(encoding='utf-8-sig')
        updated = original
        for key, value in [('TOSS_ACCOUNT_SEQ', str(seq)), ('TOSS_ENABLE_LIVE', 'false')]:
            pattern = r'^' + key + r'=.*$'
            line = key + '=' + value
            if re.search(pattern, updated, flags=re.MULTILINE):
                updated = re.sub(pattern, line, updated, flags=re.MULTILINE)
            else:
                updated = updated.rstrip('\n') + '\n' + line + '\n'
        if path.read_text(encoding='utf-8-sig') != original:
            raise BrokerError('Settings changed during lookup; retry setup')
        path.write_text(updated, encoding='utf-8')
        print(json.dumps({'status': 'configured', 'accountSeq': seq, 'liveEnabled': False}))
        return 0
    except BrokerError as exc:
        print(json.dumps({'status': 'failed', 'reason': str(exc)}))
        return 1
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'errorType': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
