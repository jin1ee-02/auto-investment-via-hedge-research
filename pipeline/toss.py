"""Toss REST adapter. Official OpenAPI 1.2.17, inspected 2026-09-14.

No automatic HTTP retries, redirects, or logging of credentials/responses.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class BrokerError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise BrokerError('Unexpected broker redirect')


class TossBroker:
    def __init__(self, *, discover_account=False):
        self.client_id = os.environ.get('TOSS_CLIENT_ID', '')
        self.secret = os.environ.get('TOSS_CLIENT_SECRET', '')
        self.account = '' if discover_account else os.environ.get('TOSS_ACCOUNT_SEQ', '')
        if not self.client_id or not self.secret or (self.account and not self.account.isdigit()):
            raise BrokerError('Configure TOSS_CLIENT_ID and TOSS_CLIENT_SECRET; TOSS_ACCOUNT_SEQ must be numeric when set')
        self.token = None
        self.expires = 0
        self.last_request = 0
        self.opener = urllib.request.build_opener(NoRedirect())
        if not discover_account and not self.account:
            accounts = self.get('accounts')
            eligible = [a for a in accounts if isinstance(a, dict) and a.get('accountType') == 'BROKERAGE'] if isinstance(accounts, list) else []
            if len(eligible) != 1 or isinstance(eligible[0].get('accountSeq'), bool) or not isinstance(eligible[0].get('accountSeq'), int):
                raise BrokerError('Set TOSS_ACCOUNT_SEQ when there is not exactly one brokerage account')
            self.account = str(eligible[0]['accountSeq'])

    def _http(self, method, path, payload=None, auth=True):
        if auth and time.monotonic() >= self.expires:
            token = self._http('POST', '/oauth2/token', {
                'grant_type': 'client_credentials', 'client_id': self.client_id,
                'client_secret': self.secret}, auth=False)
            self.token = token['access_token']
            self.expires = time.monotonic() + max(0, int(token['expires_in']) - 60)
        headers = {'Accept': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.token
            if self.account:
                headers['X-Tossinvest-Account'] = self.account
        raw = None
        if payload is not None:
            headers['Content-Type'] = 'application/json' if auth else 'application/x-www-form-urlencoded'
            raw = (json.dumps(payload) if auth else urllib.parse.urlencode(payload)).encode()
        time.sleep(max(0, 1.1 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        request = urllib.request.Request('https://openapi.tossinvest.com' + path,
                                         data=raw, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                body = json.load(response)
            if auth:
                if 'result' not in body or body.get('error'):
                    raise BrokerError('Invalid broker response')
                return body['result']
            return body
        except urllib.error.HTTPError as exc:
            # Only expose recognized error codes, never broker bodies or token data.
            code = None
            try:
                error = json.loads(exc.read(16384)).get('error')
                candidate = error.get('code') if isinstance(error, dict) else error
                if candidate in ('access_denied', 'invalid_client', 'invalid_request',
                                 'ip-not-allowed', 'account-not-found', 'account-header-required'):
                    code = candidate
            except Exception:
                pass
            stage = 'API' if auth else 'authentication'
            detail = f' ({code})' if code else ''
            if not auth and exc.code == 403:
                raise BrokerError('토스 인증이 현재 접속 IP를 허용하지 않았습니다 (HTTP 403). 토스증권 WTS > Open API > 허용 IP 관리에서 이 컴퓨터의 현재 공인 IP를 등록한 뒤 다시 실행하세요') from None
            raise BrokerError(f'Broker {stage} HTTP {exc.code}{detail}; no automatic retry') from None
        except (OSError, ValueError, KeyError):
            raise BrokerError('Broker response unavailable; no automatic retry') from None

    def get(self, path, **query):
        suffix = '?' + urllib.parse.urlencode(query) if query else ''
        return self._http('GET', '/api/v1/' + path + suffix)

    def submit(self, order):
        if os.environ.get('TOSS_ENABLE_LIVE') != 'true':
            raise BrokerError('TOSS_ENABLE_LIVE must be true for execution')
        required=('clientOrderId','symbol','side','orderType','timeInForce','quantity','price')
        if any(key not in order for key in required):
            raise BrokerError('Invalid order payload')
        result = self._http('POST', '/api/v1/orders', {key:order[key] for key in required})
        if not isinstance(result, dict) or not result.get('orderId'):
            raise BrokerError('Order acknowledgement missing; reconcile without resubmitting')
        return result
