<<<<<<< HEAD
# auto-investment-via-hedge-follow
=======
# Hedge Insight

SEC 13F를 비교해 펀드의 공통 보유와 분기 변화를 탐색하고, TradingAgents로 종목을 추가 연구한 뒤 분기별 **모의 목표 배분안**을 저장하는 프로젝트입니다. 토스 API 호출과 실제 주문 기능은 구현하지 않았습니다.

## 현재 완료된 범위

- 2026-06-30 vs 2026-03-31 실제 SEC 공시: Popular 20개 + 추가 비교 3개, 46개 스냅샷.
- Popular 목록의 20개 신고 주체를 구성하고 19개를 검증해 비교할 수 있습니다. Third Point, Viking, Lone Pine은 추가 비교 대상입니다. 총 23개 중 22개가 비교 가능합니다. 처음에는 대표 8개를 선택하고 토글로 확장할 수 있습니다.
- Duquesne은 원문 평가단가의 단위 이상 징후로 검토 상태입니다. 숫자를 임의로 1,000배 보정하지 않았습니다.
- 펀드 추가/제외 토글, 단일 펀드 보기, 동일 가중/금액 가중, 보유/확대/축소 도넛, 공통 보유, 종목 검색, 펀드별 변화와 원문 링크.
- 주식/ETF, PUT, CALL 분리. 티커가 확인되지 않은 행은 CUSIP으로 탐색 가능하고 배분에서는 제외.
- 보유 저변에 따른 시뮬레이션, 종목 비중 상한/현금 하한, JSON 내보내기.
- TradingAgents 작업 서비스, 리서치 저장/재시도/중복 방지, AI 결과를 통한 모의 배분, 일일 확인·분기별 생성 파이프라인.
- 토스 어댑터는 호출 즉시 예외를 발생시키는 비활성 경계입니다. 계좌 조회/호가 조회/인증/주문 API를 호출하는 코드가 없습니다.

**미연결:** 사용자의 LLM API 키 및 모델. 실제 LLM 네트워크 실행은 검증하지 않았고 테스트 대역으로 오케스트레이션을 검증했습니다. 화면의 보유 저변는 AI 결과가 아닙니다. Python AI 의존성은 별도 가상환경에 설치해야 합니다.

**원천 범위:** HedgeFollow Popular 페이지는 자동 접근 제한 및 자동 수집 제한 약관이 있어 크롤러를 만들지 않았습니다. 브라우저에서 2026-09-09에 확인한 Popular 20개를 모두 등록했습니다. BlackRock, Nvidia 등 전통적인 헤지펀드가 아닌 신고 주체도 원래 목록대로 포함합니다. 자체 추가 3개는 UI에서 구분합니다. 상세 데이터는 SEC 원문에서 수집했습니다. Pershing은 동일 신고 주체인 CIK 2026053의 양 분기 연결 공시를 사용합니다. 기존 CIK 1336528의 13F-NT를 빈 보유로 처리하지 않습니다.

## 로컬 대시보드 실행

Node 22.13 이상과 npm이 필요합니다.

```powershell
npm run install:ci
npm run dev
```

주소: http://localhost:5173

이 환경의 npm.cmd 경로 문제가 생기면 다음처럼 npm의 JavaScript 진입점을 직접 호출합니다.

```powershell
node 'C:/Program Files/nodejs/node_modules/npm/bin/npm-cli.js' run dev
```

프로덕션 빌드는 `npm run build`입니다. 대시보드는 Sites/Cloudflare Worker와 호환됩니다. 기본 데이터는 검증한 스냅샷을 포함하므로 API 키 없이도 탐색할 수 있습니다. 초기 페이지에는 대표 8개를 담고 전체 공시는 별도 정적 JSON으로 로딩해 Worker 메모리 사용을 줄입니다.

## LLM API 연결 방법

키를 대화에 붙여넣지 말고 로컬 `.env`에 입력하세요. `.env`, `.dev.vars`, 연구 결과, 캐시는 Git에서 제외됩니다.

1. Python 3.12+ 가상환경을 생성하고 선택적 AI 의존성을 설치합니다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r pipeline/requirements-ai.txt
Copy-Item .env.example .env
```

TradingAgents는 조사 시점의 커밋 `be952b8eccb49720509af544c6675233bc1f10d0`으로 고정했습니다. 향후 변경 시 의존성을 다시 검증하세요.

2. `.env`에서 제공자와 실제 사용 가능한 모델 ID를 설정합니다. 어떤 제공자도 자동 선택하거나 키를 자동 생성하지 않습니다.

| RESEARCH_PROVIDER | 키 변수 |
| --- | --- |
| anthropic | ANTHROPIC_API_KEY |
| openai | OPENAI_API_KEY |
| google | GOOGLE_API_KEY |
| deepseek | DEEPSEEK_API_KEY |
| openrouter | OPENROUTER_API_KEY |

```dotenv
RESEARCH_PROVIDER=openai
RESEARCH_DEEP_MODEL=YOUR_ACCOUNT_SUPPORTED_MODEL_ID
RESEARCH_QUICK_MODEL=YOUR_ACCOUNT_SUPPORTED_MODEL_ID
OPENAI_API_KEY=YOUR_SECRET_KEY
SEC_USER_AGENT=Your Name your-real-email@example.com
```

`YOUR_...`는 반드시 교체해야 할 자리표시자입니다. 깊은 분석/빠른 분석에 같은 모델을 사용할 수도 있습니다. API 요금은 사용한 제공자에서 발생하며, 모델/금액 제한은 해당 계정에서 설정하세요. 선택한 TradingAgents 데이터 제공자가 Alpha Vantage를 요구하면 `ALPHA_VANTAGE_API_KEY`도 설정합니다. 로컬 Ollama와 커스텀 endpoint는 `RESEARCH_BACKEND_URL`을 추가로 설정합니다.

3. 서비스용 임의 토큰을 생성한 뒤 `.env`에 저장합니다. 이 토큰은 LLM 키와 다릅니다.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```dotenv
RESEARCH_SERVICE_URL=http://127.0.0.1:8788
RESEARCH_SERVICE_TOKEN=GENERATED_RANDOM_TOKEN
```

동일한 두 개 `RESEARCH_SERVICE_*` 값을 프로젝트 루트 `.dev.vars`에도 넣고 대시보드 서버를 재시작합니다. LLM 제공자 키는 Python `.env`에만 필요합니다. `NODE_BINARY`는 비워 두면 PATH의 Node를 사용합니다.

4. Python 리서치 서버를 실행합니다.

```powershell
.venv/Scripts/python.exe -m pipeline.service
```

서버는 기본적으로 `127.0.0.1:8788`에만 바인딩하며 모든 API에서 토큰을 검증합니다. 대시보드에서 ‘AI 리서치 실행’을 누르면 서버가 공시 문맥을 재계산하고 작업 ID를 반환합니다. 브라우저가 상태를 조회하고 완료 보고서를 표시합니다. 같은 데이터/모델/날짜/펀드/종목 요청은 기존 작업을 재사용합니다. 실패한 요청은 재시도할 수 있습니다. 서비스 재시작 시 중단 작업은 실패 상태로 바뀝니다.

5. 후보들의 연구가 완료되면 포트폴리오 설계에서 ‘AI 결과로 최종 배분안 생성’을 누릅니다. UI와 자동 연구는 설정한 최대 종목 수(기본 8개, 최대 20개)를 사용합니다.

AI 배분 통과 조건은 `buy`, 점수 60 이상, 신뢰도 0.65 이상, `dataGaps` 없음입니다. 점수/신뢰도는 모델 판단이지 검증된 확률이 아닙니다. 적합 종목이 없으면 현금 100%이며 오류가 아닙니다. 뉴스·가격·재무 보고서가 누락되거나 스키마/출처 검증이 실패하면 배분을 생성하지 않습니다.

## 분기별 자동 파이프라인

`pipeline/strategy.json`의 펀드 목록, 가상 USD 예산, 최대 비중, 현금 하한, 종목 수를 수정합니다. 현재 예산 $10,000은 가상 예시이며 사용자 계좌 잔고가 아닙니다.

```powershell
# 최신 공시 수집 → 후보 리서치 → 제약 검증 → 모의 배분 저장
.venv/Scripts/python.exe -m pipeline.run

# 이미 수집한 데이터를 사용
.venv/Scripts/python.exe -m pipeline.run --no-refresh

# 실행해 둔 동안 매일 공시 확인, 분기/전략/원문이 같으면 기존 결과 재사용
.venv/Scripts/python.exe -m pipeline.run --watch
```

`--watch`는 실행한 프로세스가 살아 있어야 합니다. 이 작업에서는 OS 스케줄러, GitHub Actions, 자동 결제 작업 또는 실제 주문 스케줄을 설치하지 않았습니다. 컴퓨터가 꺼져도 지속하려면 Python 서비스를 상시 서버에 배포하고 이 명령을 스케줄러로 실행해야 합니다.

SQLite 트랜잭션과 파일 해시가 중복 분기 실행을 방지합니다. 분기 갱신 시 지정한 펀드의 두 분기 공시가 모두 검증되기 전에는 새 배분을 생성하지 않습니다. 이전 모의 배분은 보존됩니다. 전체 정정(RESTATEMENT)은 가장 최근 원문으로 교체합니다. 추가 보유(NEW HOLDINGS) 정정은 원문 간 중복 검토가 필요하므로 중단합니다.

출력:

- `work/research/`: 전체 종목별 보고서, 공시 문맥, 출처, 모델, 실행 시각
- `work/portfolios/`: AI 모의 배분안, 제외 사유, 제약, 현금 비중
- `work/jobs.sqlite`: UI 작업 상태
- `work/quarterly.sqlite`: 분기별 완료 상태
- `data/filings.json`: 공개 공시 스냅샷

`orders`는 빈 배열이고 `executionReady=false`입니다. 현재 보유 수량·최신 시장가격을 모르므로 목표 비중을 매수/매도 수량으로 변환하지 않습니다. 실계좌 리밸런싱과 가상 목표 배분을 구분합니다.

## 데이터 수집 / 펀드 추가

```powershell
python pipeline/collect.py --period 2026-06-30
```

`.env`를 읽는 통합 명령은 `python -m pipeline.run`입니다. 수집기를 직접 실행하면 PowerShell의 `$env:SEC_USER_AGENT`를 설정하거나 `--user-agent 'Your Name email@example.com'`을 넘겨야 합니다. 연락처를 포함한 SEC User-Agent가 필요합니다. 초기 접근 검증에는 식별용 예시 문자열을 사용했으며 지속 운영 시 본인 연락처를 넣으세요.

`pipeline/funds.json`에 펀드의 실제 SEC CIK, 이름, 표시용 스타일, HedgeFollow 경로를 추가합니다. 수집기가 SEC 신고 법인명을 대조합니다. `pipeline/strategy.json`에도 원하는 펀드를 명시해야 자동 배분에 포함됩니다. CIK가 바뀌면 서로 다른 법인의 두 분기를 임의 연결하지 마세요.

합계 검증은 원문 내부 일치 검사입니다. SEC 원문 자체의 오류까지 없음을 보장하지 않습니다. Duquesne처럼 총계가 일치해도 단위가 의심되는 원문은 별도 검사로 차단합니다. CUSIP 변경, 기업분할, 주식분할, 합병, 옵션 만기, 공시 범위 변화는 수량 차이만으로 정규화하지 않습니다.

통합 가중:

- 동일 가중: 각 펀드의 해당 종류 자산 내부 비중을 평균. 미보유 펀드는 0으로 포함.
- 금액 가중: 선택 펀드의 해당 종류 공시 금액을 합산 후 정규화.
- 확대/축소 도넛: 수량 변화 절댓값 × 최신 분기 평가단가. 청산에는 이전 분기 평가단가. 실제 거래대금이 아니며 해당 추정 금액 비율로 표시.
- 보유 저변: 현재 보유 펀드 수 / 양 분기가 완전한 선택 펀드 수. 변화는 (현재 보유 수 − 이전 보유 수) / 동일 표본 수. Chen, Hong & Stein (2002)의 ownership breadth 정의를 선택 표본에 적용. 기존 60/25/15 임의 가중 점수는 폐기.
- PUT/CALL의 13F 가치는 옵션 프리미엄이나 델타 조정 노출이 아닙니다. long/short 순노출로 합치지 않습니다.

## 호스팅 구조

Sites에는 대시보드와 서버 프록시를 배포합니다. Python TradingAgents 프로세스는 Cloudflare Worker 안에서 실행되지 않습니다. 호스팅된 사이트에서 실제 연구를 실행하려면 Python 서비스가 실행되는 서버에 HTTPS reverse proxy를 두고 다음 두 Sites 비밀값을 설정해야 합니다.

- `RESEARCH_SERVICE_URL`: 인증된 Python 서비스의 HTTPS 주소. 호스팅 상태에서 localhost는 사용할 수 없음.
- `RESEARCH_SERVICE_TOKEN`: Python 서비스와 일치하는 임의 토큰.

서비스가 연결되면 `/api/filings`도 최신 Python 데이터로 갱신하므로 매 분기 프런트엔드를 재배포할 필요가 없습니다. 연결 전에는 번들에 포함된 공시 스냅샷을 표시합니다. 제공자 비밀키를 `NEXT_PUBLIC_*` 등에 넣지 마세요. 개인 리서치 결과를 다루므로 현재 사이트의 개인 접근 설정을 유지하세요.

## 검증

```powershell
node --experimental-strip-types --test tests/domain.test.mjs
python -m unittest discover -s tests -p 'test_*.py' -v
npx tsc --noEmit
npm run build
```

테스트는 실제 공시 합계, 옵션 분리, 펀드 제외, 청산/가격 변화 구분, 가중 방식, 투자 예산/현금 상한, 미완성 리서치 차단, 출처와 수치 검증, 토스 비활성 경계를 확인합니다. AI 네트워크 호출과 토스 API 검증은 수행하지 않았습니다.

## 참고 원문

- [HedgeFollow Popular](https://hedgefollow.com/popular-hedge-funds.php)
- [HedgeFollow 이용조건](https://hedgefollow.com/terms.php)
- [SEC 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f)
- [TradingAgents](https://github.com/TauricResearch/TradingAgents) — Apache-2.0, 선택적 의존성으로 사용하며 원본 코드를 복사하지 않음
- [토스증권 공식 API 문서](https://developers.tossinvest.com/docs) — 문서 참조만 했으며 실제 API 연결 없음

## 공시 일정과 분기 활동 기반 리서치

화면 상단에서 현재 보유 기준 분기와 다음 분기의 SEC 제출 마감을 확인합니다. 펀드별 확정 발표일이 아닙니다.

현재 AI 후보는 신규·확대 펀드가 2개 이상이거나 축소·청산 펀드가 2개 이상인 주식·ETF입니다. 현재 보유가 0인 전량 청산 종목도 포함합니다. 보유 유지, 옵션, 티커 미확인 종목은 제외합니다.

우선순위는 max(확대 수, 축소 수) 내림차순, 동률이면 해당 수 / (확대 수 + 축소 수) 내림차순, 다시 동률이면 식별자순입니다. 동일 티커를 한 번만 조사하고 기본 8개·최대 20개로 제한합니다. UI·자동 파이프라인이 동일한 규칙을 사용합니다. 보유 저변은 참고 데이터로만 남고 후보 순위에 사용하지 않습니다.

매도 우세와 매수·매도 동률 종목은 위험 점검 대상이며 매수 배분에서 제외합니다. 모의 배분은 조사 대상 중 확대 2개 이상·확대 수가 축소 수보다 큰 종목에 확대 펀드 수로 가중합니다. AI 최종 배분은 이 조건에 추가로 AI buy·점수·신뢰도·근거 요건을 적용합니다. 매도 신호로 숏 주문을 만들지 않습니다.

13F는 분기 말 순수량 비교이므로 실제 거래일, 분기 내 왕복매매, 지금의 진입 타이밍을 알 수 없습니다. 주식분할 등 기업행동도 확인해야 합니다. AI는 현재 가격·거래량·촉매·실적 일정을 재검토하고 최신 근거가 없으면 dataGaps에 기록합니다. 검증된 스윙 수익률 공식이 아닌 리서치 우선순위 규칙입니다.

같은 날짜·펀드·공시·모델·리서치 방식의 결과를 재사용합니다. 수집 시각만 달라져도 캐시를 폐기하지 않습니다. 방식 변경 전 보고서는 새 실행에서 재사용하지 않습니다.

## 보고서 읽기와 진행 상태

AI 리서치 카드의 ‘보고서 전문 읽기’에서 종합 판단, 위험, 미확인 근거, 6개 분석 보고서와 출처를 확인합니다. JSON 저장은 선택 사항입니다. 기존 완료 작업은 같은 조건에서 서버 캐시로 다시 열 수 있습니다.

진행률은 공시 준비, 시장, 뉴스, 재무, 강세·약세 검토, 매매안, 리스크, 공통 변화 종합, 검증·저장의 9단계 완료 비율입니다. TradingAgents의 LangGraph 노드 완료 콜백에서 보고서 생성 여부를 확인합니다. 도구 호출을 위한 중간 반복은 완료로 계산하지 않습니다. 토큰 비율이나 남은 시간 예측이 아니며, 동일 단계에서 오래 걸릴 수 있습니다. 오류 시 마지막 진행 단계를 보존합니다.

브라우저는 3초마다 상태를 조회하며, 작업 ID만 로컬에 저장해 새로고침 후 다시 연결합니다. 원시 프롬프트나 내부 추론 대신 단계명과 상태만 전달합니다. 기존 서버에서 이미 시작된 작업은 상세 진행률을 제공하지 못할 수 있습니다.

TradingAgents는 시장·뉴스·재무 분석 후 강세/약세 연구자와 연구 책임자, Trader, 공격적/보수적/중립 리스크 분석자와 포트폴리오 책임자를 순차 실행합니다. 토론 설정은 각 1라운드입니다. 그 뒤 앱의 별도 심층 모델 호출이 13F 공통 매매 변화와 스윙 검토 목적을 결합하고 구조화된 판단을 검증합니다. 소셜 분석은 선택하지 않습니다. Trader/포트폴리오 책임자도 의견만 작성하며 주문하지 않습니다.

AI 리서치 화면은 전체 적격 후보를 페이지당 8개씩 숫자 페이지로 탐색합니다. 20위 밖의 종목도 개별 실행할 수 있습니다. 페이지 이동은 AI를 호출하지 않습니다. 자동 포트폴리오의 조사 한도는 별도이며 기본 8개·최대 20개를 유지합니다.
