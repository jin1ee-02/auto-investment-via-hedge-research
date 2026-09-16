# Hedge Insight

SEC 13F 공통 변화 후보를 TradingAgents로 조사하고, 토스증권의 최신 계좌 상태로 매매안을 만드는 로컬 투자 리서치 도구입니다. 분기 공시는 리서치 데이터이며 자동 주문 트리거가 아닙니다. 실제 주문은 웹에서 실행되지 않고, 로컬 터미널의 명시적 승인과 `TOSS_ENABLE_LIVE=true`가 모두 있어야만 열립니다.

## 현재 흐름

1. 웹에서 원하는 펀드와 후보 조건을 선택합니다.
2. 리서치 종목 수(1~8개, 기본 6개)를 고르고 `리서치하고 매매안 만들기`를 누르면 같은 방향 펀드 수 → 방향 일치율 → 안정적인 종목 키 순으로 상위 후보를 고릅니다.
3. 선택한 수만큼 순차 조사합니다. 같은 공시·펀드·모델·날짜·판단 기준의 완료 보고서는 재사용합니다.
4. 토스에서 미국주식 보유, USD 매수가능금액, 미체결 주문과 현재가를 읽습니다.
5. TradingAgents Portfolio Manager의 최종 5단계 등급으로 매수·매도·유지를 정하고 웹에 한 번에 표시합니다. 별도의 AI 매매 신호는 만들지 않습니다.
6. 주문이 가능한 상태이면 15분짜리 승인 보고서를 만듭니다. 웹은 검토만 하며 주문 POST를 제공하지 않습니다.

후보 하나라도 실패하거나 불완전하면 완료된 부분 보고서는 보존하지만 승인 가능한 주문안은 만들지 않습니다. 같은 분기에도 언제든 새 파이프라인을 실행할 수 있고, 매번 새 `runId`·`batchId`와 최신 계좌 스냅샷을 사용합니다.

## 주문 게이트와 운용 제한

2026-09-15 사용자 요청으로 금액·비중 제한을 일시 해제했습니다. 현재 `pipeline/strategy.json`은 종목당 최대 100%, 최소 현금 0%, 제안당 거래 합계 최대 자본 100%, 최소 주문 $0입니다. 매도대금을 같은 제안의 매수 재원으로 쓰지 않으므로 자본 100%는 별도의 회전율 제한 없이 현재 가용 현금 범위에서 거래할 수 있는 설정입니다. 비용 여유 1%, 최대 보유 6개, 리서치·시세·계좌 검증 및 주문 승인 조건은 유지합니다. 복원 시 `pipeline/strategy.standard.json`의 네 값(`maxWeight`, `minCash`, `maxTurnover`, `minTradeUsd`)을 현재 설정에 반영하세요. 자동 복원 날짜는 지정하지 않았습니다.

- 매수: 확대 우세 후보이면서 TradingAgents가 `Buy/Overweight`일 때만 생성합니다.
- 매도: 축소 우세 후보이면서 현재 보유한 미국주식에 TradingAgents가 `Sell/Underweight`를 부여했을 때만 생성합니다.
- `Hold`·13F와 등급 불일치·미조사·치명적 데이터 무결성 문제 종목은 유지합니다. 공매도, 신용, 환전, 국내주식 매도는 만들지 않습니다.
- 배분 점수는 `TradingAgents 등급 강도 × (같은 방향 펀드 수 ÷ 선택 펀드 수)`입니다. `Buy/Sell=100`, `Overweight/Underweight=80`, `Hold=0`으로 계산합니다.
- 현재 서버 설정은 종목당 100%, 현금 0%, 제안당 회전율 100%, 최소 주문 $0, 비용 여유 1%입니다. 표준 설정은 `pipeline/strategy.standard.json`에 보존되어 있습니다.
- 투자 가능 자본은 `USD 현금 매수가능금액 + 미국주식 평가액`입니다. KRW·국내주식은 제외 자산으로만 표시합니다.
- 미조사 미국 보유는 보호 자산입니다. 기존 보유가 한도를 넘으면 강제 매도하지 않고 신규 개설을 막습니다.
- 매도 예상대금은 같은 주문안의 매수 재원으로 사용하지 않습니다.
- 미체결 주문이 있거나 현재가가 5분보다 오래되면 목표안만 표시하고 실행 가능한 주문안을 만들지 않습니다.

## 로컬 실행

Node 22.13+, Python 3.12+가 필요합니다.

```powershell
npm run install:ci
.venv/Scripts/python.exe -m pip install -r pipeline/requirements-ai.txt
npm run dev
.venv/Scripts/python.exe -m pipeline.service
```

대시보드는 기본적으로 `http://localhost:5173`, Python 서비스는 `http://127.0.0.1:8788`에서 실행됩니다. `RESEARCH_SERVICE_TOKEN`은 양쪽 서버 설정에만 두며 브라우저로 전달되지 않습니다.

리서치 서버는 OpenAI·시장 데이터·토스 API로 외부 HTTPS 연결이 가능한 터미널에서 시작해야 합니다. 네트워크가 제한된 에이전트 실행 환경에서는 서버의 로컬 health 응답이 정상이어도 리서치가 실패할 수 있습니다. Windows 소켓 오류 10013이 발생하면 해당 서버를 종료하고 네트워크 접근이 허용된 환경에서 위 명령으로 재시작하세요. `work/research/`와 `work/jobs.sqlite`는 삭제하지 마세요. 같은 입력·날짜의 완료 보고서는 재실행 시 재사용됩니다.

`.env.example`을 참고해 LLM 제공자와 토스 자격 증명을 설정합니다. `TOSS_ACCOUNT_SEQ`는 종합매매 계좌가 정확히 하나면 비워 둘 수 있고, 여러 개면 명시해야 합니다. `TOSS_ENABLE_LIVE=false`인 상태에서도 계좌·보유·매수가능금액·미체결·시세 조회와 주문안 검증은 가능합니다.

Python 서비스 API:

- `POST /pipelines`: `{ fundIds, candidateFilter?, candidateCount? }` (`candidateCount`는 1~8, 기본 6)
- `GET /pipelines/{runId}`: 후보, 리서치 진행률, 계좌 요약, 목표 비중, 제외 사유, 주문안, 승인 보고서
- Next 동일 출처 프록시: `POST/GET /api/pipeline`

고급 로컬 실행:

```powershell
# 토스 조회 후 승인 보고서까지만 생성. 주문 전송 없음.
.venv/Scripts/python.exe -X utf8 -m pipeline.run --broker toss

# 보고서 검토 후에만 사용. 이어서 정확히 APPROVE <reviewId>를 입력해야 함.
.venv/Scripts/python.exe -X utf8 -m pipeline.run --broker toss --approve REVIEW_ID

# 알려진 주문 ID의 상태 조회만 수행하며 재전송하지 않음.
.venv/Scripts/python.exe -X utf8 -m pipeline.run --broker toss --reconcile
```

`--watch`와 무인 `--live`는 차단되어 있습니다. 승인 실행도 `.env`의 `TOSS_ENABLE_LIVE=true`가 아니면 실패합니다. 자세한 계약은 [QUARTERLY_TRADING.md](QUARTERLY_TRADING.md)를 참고하세요.

## 데이터와 결과

- `data/filings.json`: 검증된 SEC 공시 스냅샷
- `work/research/`: 재사용 가능한 종목별 완료 보고서
- `work/portfolios/`: 계좌 스냅샷과 목표 배분·주문안
- `work/approvals/`: 사람이 읽는 JSON/HTML 승인 보고서
- `work/jobs.sqlite`: 파이프라인 진행 상태
- `work/execution.sqlite`: 승인과 계좌+batch 원장

13F는 분기 말 보유 스냅샷이라 실제 거래일, 분기 중 왕복매매, 현재 진입 시점을 알려주지 않습니다. 화면의 신호 강도는 TradingAgents 최종 등급을 `Buy/Sell=100`, `Overweight/Underweight=80`, `Hold=50`으로 표시한 값이며 검증된 수익 확률이나 별도 신뢰도가 아닙니다. 배분 계산에서는 Hold를 0으로 취급합니다.

## 검증

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"
node --experimental-strip-types --test tests/*.test.mjs
npm run lint
npm run build
```

테스트는 후보 6개 제한과 순위, 신호 게이트, 미국 자산만 사용하는 배분, 보호 보유, 현금·종목·회전율·최소 주문·비용 제한, 미체결·시세 만료, 동일 분기 다중 batch, 승인 변조·만료·소모, 응답 불명 재전송 금지를 검증합니다. 실제 주문 POST는 테스트나 읽기 전용 연결 검증에서 호출하지 않습니다.

## 참고

- [SEC Form 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f)
- [TradingAgents](https://github.com/TauricResearch/TradingAgents)
- [토스증권 공식 OpenAPI 1.2.17](https://openapi.tossinvest.com/openapi-docs/latest/openapi.json)
