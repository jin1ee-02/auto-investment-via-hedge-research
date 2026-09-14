"""One durable order batch per account and filing quarter; USD integer LIMIT orders."""
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, ROUND_DOWN
from urllib.parse import quote
from .research import ROOT


def number(value):
    if isinstance(value, bool):
        raise ValueError('Invalid numeric input')
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('Expected finite nonnegative number')
    return result


def validate_config(config):
    for name in ('budgetUsd', 'maxWeight', 'maxTurnover', 'minTradeUsd', 'feeBuffer'):
        if number(config[name]) <= 0:
            raise ValueError('Invalid ' + name)
    for name in ('maxWeight', 'maxTurnover'):
        if number(config[name]) > 1:
            raise ValueError(name + ' must be at most 1')
    if not 0 <= number(config['minCash']) < 1 or number(config['feeBuffer']) > Decimal('.1'):
        raise ValueError('Invalid cash or fee buffer')
    if type(config['maxHoldings']) is not int or not 1 <= config['maxHoldings'] <= 20:
        raise ValueError('Invalid maxHoldings')
    if not config['fundIds'] or len(set(config['fundIds'])) != len(config['fundIds']):
        raise ValueError('Select unique funds')
    dt.date.fromisoformat(config['startPeriod'])


def draft_orders(plan, broker, config):
    """Keep unresearched/watch/gap positions; sell only researched avoid or buy excess."""
    validate_config(config)
    created = dt.datetime.fromisoformat(plan['createdAt'])
    if not created.tzinfo or not 0 <= (dt.datetime.now(dt.timezone.utc)-created).total_seconds() <= 7*86400:
        raise ValueError('Research plan expired; no automatic mid-quarter research')
    if broker.get('orders', status='OPEN')['orders']:
        raise ValueError('Open orders exist; wait before creating the quarterly batch')
    holdings = broker.get('holdings')['items']
    held = {}
    for item in holdings:
        if item['currency'] == 'USD' and item['marketCountry'] == 'US':
            if item['symbol'] in held:
                raise ValueError('Duplicate holding')
            held[item['symbol']] = number(item['quantity'])
    power = broker.get('buying-power', currency='USD')
    if power['currency'] != 'USD':
        raise ValueError('Unexpected buying-power currency')
    cash = number(power['cashBuyingPower'])
    targets = {p['ticker']: number(p['amount']) for p in plan['portfolio']['positions']}
    decisions = {r['ticker']: r['decision'] for r in plan['research']}
    signals = {r['ticker']: str(r.get('upstreamSignal', '')).lower() for r in plan['research']}
    symbols = sorted(set(held) | set(targets))
    if not symbols:
        return []
    if any(not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,19}', s) for s in symbols):
        raise ValueError('Invalid US symbol')
    prices = {}
    for item in broker.get('prices', symbols=','.join(symbols)):
        timestamp = dt.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
        age = (dt.datetime.now(dt.timezone.utc)-timestamp).total_seconds()
        price = number(item['lastPrice'])
        if item['currency'] != 'USD' or not 0 <= age <= 300 or price < 1:
            raise ValueError('Require fresh USD quotes >= $1; wait for a trading session')
        prices[item['symbol']] = price.quantize(Decimal('.01'), rounding=ROUND_DOWN)
    if any(s not in prices for s in symbols):
        raise ValueError('Missing quote')
    budget = min(number(config['budgetUsd']), cash + sum(held[s]*prices[s] for s in held))
    available = max(Decimal(0), cash-budget*number(config['minCash']))
    turnover = budget*number(config['maxTurnover'])
    orders = []
    # Sells first for clarity; proceeds are never counted as available buy cash.
    changes = []
    for symbol in symbols:
        decision = decisions.get(symbol)
        if not decision or decision['dataGaps'] or number(decision['confidence']) < Decimal('.65'):
            continue
        if decision['stance'] == 'avoid':
            if signals.get(symbol) != 'sell':
                continue
            target = Decimal(0)
        elif decision['stance'] == 'buy' and symbol in targets:
            if signals.get(symbol) not in ('buy', 'overweight'):
                continue
            target = min(targets[symbol], budget*number(config['maxWeight']))
        else:
            continue
        quantity = int(target/prices[symbol])-int(held.get(symbol, 0))
        if quantity:
            changes.append((quantity > 0, symbol, quantity))
    for _, symbol, change in sorted(changes):
        price = prices[symbol]
        quantity = min(abs(change), int(turnover/price))
        if change > 0:
            quantity = min(quantity, int(available/(price*(1+number(config['feeBuffer'])))))
            if not held.get(symbol) and sum(q > 0 for q in held.values()) >= config['maxHoldings']:
                continue
        else:
            quantity = min(quantity, int(number(broker.get('sellable-quantity', symbol=symbol)['sellableQuantity'])))
        amount = quantity*price
        if not quantity or amount < number(config['minTradeUsd']):
            continue
        side = 'BUY' if change > 0 else 'SELL'
        key = hashlib.sha256(f'{broker.account}:{plan["period"]}:{symbol}:{side}'.encode()).hexdigest()[:32]
        orders.append({'clientOrderId': key, 'symbol': symbol, 'side': side,
                       'orderType': 'LIMIT', 'timeInForce': 'DAY',
                       'quantity': str(quantity), 'price': str(price)})
        turnover -= amount
        if change > 0:
            available -= amount*(1+number(config['feeBuffer']))
            held[symbol] = held.get(symbol, Decimal(0))+quantity
    return orders


@contextmanager
def ledger():
    (ROOT/'work').mkdir(exist_ok=True)
    db = sqlite3.connect(ROOT/'work/execution.sqlite', timeout=30)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS batches (account TEXT, period TEXT, result TEXT NOT NULL, PRIMARY KEY(account,period))')
    try:
        with db:
            yield db
    finally:
        db.close()


def execute_once(plan, broker, config, live=False):
    if not live:
        return {'status': 'dry_run', 'executed': False, 'orders': draft_orders(plan, broker, config)}
    if os.getenv('TOSS_ENABLE_LIVE') != 'true' or (ROOT/'work/STOP_TRADING').exists():
        raise ValueError('Live execution disabled or STOP_TRADING present')
    with ledger() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT result FROM batches WHERE account=? AND period=?', (broker.account, plan['period'])).fetchone()
        if existing:
            return json.loads(existing[0])
        previous = db.execute('SELECT period,result FROM batches WHERE account=?', (broker.account,)).fetchall()
        if any(p >= plan['period'] for p, _ in previous):
            raise ValueError('Older quarter cannot execute')
        if any(json.loads(r)['status'] in ('submitting', 'needs_reconciliation') for _, r in previous):
            raise ValueError('An earlier batch requires reconciliation')
        orders = draft_orders(plan, broker, config)
        result = {'status': 'submitting', 'period': plan['period'], 'planId': plan['id'],
                  'executed': False, 'orders': [{'request': o, 'state': 'not_sent'} for o in orders]}
        # Commit intent BEFORE the first HTTP POST. A crash never causes re-submission.
        db.execute('INSERT INTO batches VALUES (?,?,?)', (broker.account, plan['period'], json.dumps(result)))
        db.commit()
        for item in result['orders']:
            item['state'] = 'unknown'
            db.execute('UPDATE batches SET result=? WHERE account=? AND period=?', (json.dumps(result), broker.account, plan['period']))
            db.commit()
            try:
                if (ROOT/'work/STOP_TRADING').exists():
                    raise ValueError('Stopped')
                acknowledgement = broker.submit(item['request'])
                item.update(state='submitted', orderId=acknowledgement['orderId'])
                result['executed'] = True
            except Exception:
                result['status'] = 'needs_reconciliation'
                break
            finally:
                db.execute('UPDATE batches SET result=? WHERE account=? AND period=?', (json.dumps(result), broker.account, plan['period']))
                db.commit()
        if result['status'] == 'submitting':
            result['status'] = 'submitted' if orders else 'no_orders'
        db.execute('UPDATE batches SET result=? WHERE account=? AND period=?', (json.dumps(result), broker.account, plan['period']))
        return result


def reconcile(broker):
    """Read order details only; no replacement, cancellation, or fresh orders."""
    results = []
    with ledger() as db:
        for period, raw in db.execute('SELECT period,result FROM batches WHERE account=?', (broker.account,)).fetchall():
            result = json.loads(raw)
            for item in result['orders']:
                if item.get('orderId'):
                    detail = broker.get('orders/' + quote(item['orderId'], safe=''))
                    item['brokerStatus'] = detail['status']
                    item['execution'] = detail.get('execution')
            # Unknown acknowledgements remain blocked: do not infer an absent order is safe to retry.
            db.execute('UPDATE batches SET result=? WHERE account=? AND period=?', (json.dumps(result), broker.account, period))
            results.append(result)
    return results
