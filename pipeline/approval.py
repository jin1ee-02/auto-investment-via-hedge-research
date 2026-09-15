"""Durable, expiring approval of an exact account, research plan and order batch."""
import datetime as dt
import hashlib
import html
import json
import uuid
from . import execution


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def table(db):
    db.execute('CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL)')


def get_review(review_id):
    with execution.ledger() as db:
        table(db)
        row=db.execute('SELECT status,payload FROM reviews WHERE id=?',(review_id,)).fetchone()
    if not row:raise ValueError('Unknown approval report')
    return {**json.loads(row[1]),'status':row[0]}


def prepare_review(plan,broker,config,orders=None):
    if execution.has_unresolved_batch(broker.account):
        raise ValueError('An earlier batch requires reconciliation')
    orders=execution.draft_orders(plan,broker,config) if orders is None else orders
    basis={'account':str(broker.account),'plan':plan,'config':config,'orders':orders}
    now=dt.datetime.now(dt.timezone.utc)
    with execution.ledger() as db:
        table(db)
        for status,raw in db.execute("SELECT status,payload FROM reviews WHERE status='pending'").fetchall():
            saved=json.loads(raw)
            if saved['basisHash']==digest(basis) and dt.datetime.fromisoformat(saved['expiresAt'])>now:
                return {**saved,'status':status}
        review={**basis,'schemaVersion':1,'id':uuid.uuid4().hex,'status':'pending','basisHash':digest(basis),'createdAt':now.isoformat(),'expiresAt':(now+dt.timedelta(minutes=15)).isoformat()}
        db.execute('INSERT INTO reviews VALUES (?,?,?)',(review['id'],'pending',json.dumps(review,ensure_ascii=False)))
    # Files are review artifacts only. Execution always reads the original SQLite record.
    folder=execution.ROOT/'work/approvals';folder.mkdir(parents=True,exist_ok=True)
    public={**review,'account':'••••'+str(broker.account)[-4:]}
    (folder/(review['id']+'.json')).write_text(json.dumps(public,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=''.join('<tr>'+''.join('<td>'+html.escape(str(order[k]))+'</td>' for k in ('symbol','side','quantity','price'))+'<td>'+str(execution.number(order['quantity'])*execution.number(order['price']))+'</td><td>'+html.escape(str(order.get('rationale','')))+'</td></tr>' for order in orders)
    buy_total=sum(execution.number(o['quantity'])*execution.number(o['price']) for o in orders if o['side']=='BUY')
    sell_total=sum(execution.number(o['quantity'])*execution.number(o['price']) for o in orders if o['side']=='SELL')
    research=''.join('<article><h3>'+html.escape(r['ticker'])+'</h3><pre>'+html.escape(json.dumps(r['decision'],ensure_ascii=False,indent=2))+'</pre></article>' for r in plan.get('research',[]))
    command=f'.venv/Scripts/python -X utf8 -m pipeline.run --broker toss --approve {review["id"]}'
    content=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>주문 승인 검토</title><style>body{{max-width:1000px;margin:60px auto;padding:24px;background:#0b0c0e;color:#ededf0;font:16px/1.7 system-ui}}h1{{font-size:36px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #303138}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;padding:20px;background:#17181c}}article{{border-top:1px solid #303138;padding-top:12px}}</style><h1>주문 전, 최종 확인</h1><p>승인 대기 · {html.escape(plan['period'])} · 계좌 {html.escape(public['account'])}</p><p>유효 기한 {review['expiresAt']} (UTC). 지정가 DAY · USD · 접수와 체결은 다릅니다.</p><table><tr><th>종목</th><th>방향</th><th>수량</th><th>지정가 USD</th></tr>{rows}</table><h2>리서치 판단과 위험</h2>{research}<h2>확인 후 실행</h2><p>아래 명령을 로컬 터미널에서 직접 실행하세요. 터미널에서 주문안을 다시 표시하고 최종 승인 문구를 요청합니다. 주문안이 변경되면 새 보고서가 필요합니다.</p><pre>{html.escape(command)}</pre><p>승인하지 않으면 주문은 전송되지 않습니다.</p></html>'''
    content=content.replace('<th>지정가 USD</th>','<th>지정가 USD</th><th>금액 USD</th><th>판단 근거</th>').replace('<h2>리서치 판단과 위험</h2>',f'<p>총 매수 ${buy_total} · 총 매도 ${sell_total} · 수수료 별도. 실제 체결 가격·수량에 따라 달라집니다.</p><h2>운용 제약과 후보 조건</h2><pre>{html.escape(json.dumps(config,ensure_ascii=False,indent=2))}</pre><h2>리서치 판단과 위험</h2>')
    (folder/(review['id']+'.html')).write_text(content,encoding='utf-8')
    return review


def decide_review(review_id,phrase,reject=False):
    with execution.ledger() as db:
        table(db);db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT status,payload FROM reviews WHERE id=?',(review_id,)).fetchone()
        if not row or row[0]!='pending':raise ValueError('Review is not pending')
        review=json.loads(row[1])
        if dt.datetime.fromisoformat(review['expiresAt'])<=dt.datetime.now(dt.timezone.utc):raise ValueError('Approval report expired; prepare a fresh report')
        if not reject and phrase!='APPROVE '+review_id:raise ValueError('Exact approval phrase required; no orders sent')
        review['decisionAt']=dt.datetime.now(dt.timezone.utc).isoformat()
        review['status']='rejected' if reject else 'approved'
        db.execute('UPDATE reviews SET status=?,payload=? WHERE id=?',(review['status'],json.dumps(review,ensure_ascii=False),review_id))
    return review


def require_approval(db,review_id,plan,broker,config,orders):
    table(db)
    row=db.execute('SELECT status,payload FROM reviews WHERE id=?',(review_id,)).fetchone() if review_id else None
    if not row or row[0]!='approved':raise ValueError('Explicit approval required; prepare and review the order report first')
    review=json.loads(row[1])
    if dt.datetime.fromisoformat(review['expiresAt'])<=dt.datetime.now(dt.timezone.utc):raise ValueError('Approval expired; review fresh orders')
    if review['basisHash']!=digest({'account':str(broker.account),'plan':plan,'config':config,'orders':orders}):raise ValueError('Account, research, settings or orders changed; new approval required')
    db.execute("UPDATE reviews SET status='consumed' WHERE id=?",(review_id,))
