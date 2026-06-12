# 🏠 아파트 실거래가 자동 모니터링

국토교통부 **아파트 매매 실거래가 상세 자료** API(`RTMSDataSvcAptTradeDev`)로
관심 단지의 신규 거래를 매일 감지해 **텔레그램 알림**을 보내고,
`state.json`에 누적 기록하며 **대시보드**(`docs/index.html`)를 자동 갱신합니다.

## 동작 방식

1. 매일 오전 9시(KST) GitHub Actions가 실행 (신고 지연 대비 **이번 달 + 지난달** 조회)
2. `config.yaml`의 관심 단지와 매칭 후 `state.json`의 기존 기록과 비교해 **신규 거래만** 감지
3. 신규 거래 발견 시 텔레그램 알림 — 단지명·전용면적·층·거래금액·계약일·**직전 동일 평형 거래 대비 등락**
4. 거래 **해제(취소)** 도 감지해 알림
5. 갱신된 `state.json`과 대시보드를 자동 커밋

> **최초 실행** 시에는 기존 거래 전체를 기준선으로 저장만 하고 알림은 보내지 않습니다
> (알림 폭탄 방지). 이후 실행부터 새로 등록된 거래만 알립니다.

## 1. 설치 및 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env   # .env에 인증키 입력
python monitor.py              # 실행
python monitor.py --dry-run    # 알림/저장 없이 감지 결과만 확인
```

`.env` 파일:

```
MOLIT_API_KEY=공공데이터포털_일반인증키(Decoding)
TELEGRAM_BOT_TOKEN=123456:ABC-...
TELEGRAM_CHAT_ID=123456789
```

## 2. 관심 단지 설정 (config.yaml)

```yaml
complexes:
  - name: 송도더샵 (전용 84)
    region: 인천 연수구      # 시군구명 → 법정동코드 5자리 자동 변환
    match: ["송도더샵"]      # 단지명 부분일치 키워드 (생략 시 name 사용)
    areas: [84]              # 전용면적 ㎡ 정수 대역. 생략하면 전체 면적
```

- `region`은 `인천 연수구`, `인천광역시 연수구`, `성남시 분당구` 등 자연스러운 표기 모두 인식합니다.
  전국 시군구 매핑은 [sgg_codes.json](sgg_codes.json)에 내장되어 있습니다(행정표준코드관리시스템 기준).
- 같은 이름의 시군구가 여러 곳이면(예: 고성군) 시도명을 포함해 쓰거나 `lawd_cd`를 직접 지정하세요.

## 3. (선택) 텔레그램 봇 토큰 / chat_id 발급법

> 텔레그램 알림이 필요 없으면 이 섹션은 건너뛰어도 됩니다.
> 토큰을 설정하지 않으면 알림 없이 기록·대시보드 갱신만 수행합니다.

### 봇 토큰 발급

1. 텔레그램에서 **@BotFather** 검색 → 대화 시작
2. `/newbot` 입력 → 봇 이름 입력(예: `우리집 실거래 알림`) → 봇 아이디 입력(`_bot`으로 끝나야 함, 예: `my_apt_alert_bot`)
3. BotFather가 알려주는 `123456789:AAH4f...` 형태의 문자열이 **봇 토큰**입니다

### chat_id 확인

1. 방금 만든 내 봇을 검색해 **대화 시작(Start) 버튼을 꼭 누르고** 아무 메시지나 한 번 보냅니다
2. 브라우저에서 아래 주소를 엽니다 (토큰 부분 교체):
   ```
   https://api.telegram.org/bot<봇토큰>/getUpdates
   ```
3. 응답 JSON에서 `"chat":{"id":123456789,...}`의 숫자가 **chat_id**입니다
   - 간편하게는 **@userinfobot**에게 아무 메시지나 보내면 내 ID를 알려줍니다
   - 그룹방으로 받으려면 봇을 그룹에 초대한 뒤 같은 방법으로 확인 (그룹 ID는 `-`로 시작)

## 4. GitHub Actions 자동 실행 설정

1. 이 폴더를 GitHub 저장소로 푸시
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 등록:

   | Secret 이름 | 값 | 필수 |
   |---|---|---|
   | `MOLIT_API_KEY` | 공공데이터포털 일반 인증키(Decoding) | ✅ |
   | `TELEGRAM_BOT_TOKEN` | 봇 토큰 | 선택 |
   | `TELEGRAM_CHAT_ID` | chat_id | 선택 |

3. **Actions 탭**에서 워크플로를 한 번 수동 실행(`Run workflow`)해 기준선을 만들어 두면 좋습니다
4. 이후 매일 **오전 9시(KST)** 자동 실행됩니다
   - 시간 변경: [.github/workflows/monitor.yml](.github/workflows/monitor.yml)의 `cron` 수정 (UTC 기준, KST−9시간. 예: 8시 KST → `0 23 * * *`)
   - GitHub Actions 무료 플랜 특성상 수분~수십분 지연될 수 있습니다

## 5. 대시보드

실행할 때마다 [docs/index.html](docs/index.html)이 갱신됩니다.

- **로컬**: 파일을 브라우저로 열면 끝 (외부 라이브러리/CDN 불필요)
- **웹에서 보기**: 저장소 **Settings → Pages → Branch: `main`, 폴더 `/docs`** 로 설정하면
  `https://<아이디>.github.io/<저장소>/` 에서 항상 최신 대시보드를 볼 수 있습니다

구성: 단지·평형별 요약 카드(최신가·직전 대비 등락) / 가격 추이 차트 / 전체 거래 테이블(해제 거래는 취소선 표시)

## 파일 구조

```
monitor.py        # 메인: 조회 → 신규 감지 → 텔레그램 알림 → state/대시보드 갱신
dashboard.py      # state.json → docs/index.html 생성
lawd.py           # 시군구명 → 법정동코드 변환
sgg_codes.json    # 전국 시군구 법정동코드 매핑 (code.go.kr 기준)
config.yaml       # 관심 단지 설정
state.json        # 누적 거래 기록 (자동 생성·커밋)
docs/index.html   # 대시보드 (자동 생성·커밋)
```

## 참고: API 명세 (기술문서 기준)

- 엔드포인트: `https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev`
- 요청: `serviceKey`, `LAWD_CD`(법정동코드 5자리), `DEAL_YMD`(YYYYMM), `pageNo`, `numOfRows`
- 응답(XML): `aptNm` 단지명, `excluUseAr` 전용면적, `floor` 층, `dealAmount` 거래금액(만원),
  `dealYear/Month/Day` 계약일, `cdealType` 해제여부(`O`=해제), `dealingGbn` 거래유형 등
- 데이터 갱신주기: 일 1회 / ⚠ data.go.kr는 기본 curl/스크립트 User-Agent를 차단하므로 브라우저 UA로 호출
