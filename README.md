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
- ⚠ **`match`는 실제 등록 단지명과 정확히 일치**해야 합니다. 예: `이매삼성`(❌) → 실제 등록명은
  `이매촌(삼성)`(✅). 괄호·'촌' 같은 글자까지 포함해야 매칭됩니다.
- ⚠ **`areas`는 실제 존재하는 전용면적**이어야 합니다. 같은 평형이라도 전용면적은 단지마다 다릅니다.

### 단지명·전용면적 확인 (search.py)

`match`/`areas`를 정확히 적기 어려우면, 실제 API에 등록된 단지명·전용면적을 조회하세요:

```bash
python search.py "경기도 용인시 수지구"            # 그 지역 전체 단지(최근 6개월)
python search.py "경기도 용인시 수지구" 수지삼성     # 키워드 포함 단지만
python search.py 41135 이매촌 --months 12          # 코드 직접 지정 + 기간 지정
```

출력된 단지명을 `match`에, 원하는 전용면적 정수를 `areas`에 그대로 적으면 됩니다.

> **대시보드는 항상 현재 config의 단지만 보여줍니다.** 관심단지에서 뺀 단지의 기록은
> 다음 실행 때 자동으로 정리되어 현황판에서 사라집니다. 매칭이 0건인 단지는 대시보드 상단에
> 노란 경고 배너로 표시되니, 그때 `match`/`areas`를 점검하세요.

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

### 📊 대시보드 탭

- 단지·평형별 요약 카드 (최신가·직전 대비 등락)
- 가격 추이 차트 (단지·평형 선택)
- 거래 내역 — 드롭다운으로 **전체(최신순) / 전체(단지별 묶음) / 특정 단지**를 골라볼 수 있고,
  해제 거래는 취소선으로 표시됩니다

### ⚙️ 단지 관리 탭

대시보드에서 직접 관심 단지를 추가·수정·삭제하고 GitHub에 저장할 수 있습니다.

1. 표에서 단지를 편집 (지역명 입력 시 법정동코드가 즉시 변환되어 표시됨)
2. 저장소 소유자/이름(github.io 주소로 열면 자동 입력)과 **GitHub 토큰**(repo·workflow 권한)을 입력
3. **"💾 저장하고 지금 실행 ▶"** 클릭 → config.yaml 커밋 + 모니터링 실행이 한 번에 됩니다
4. **2~3분 후 페이지를 새로고침**(Shift+새로고침)하면 현황판에 반영됩니다

> ⚠ **"저장만"으로는 현황판이 바뀌지 않습니다.** config 저장은 설정만 바꿀 뿐이고,
> 실제 데이터 조회·집계(모니터링 실행)가 돌아야 대시보드가 갱신됩니다. 그래서
> **"저장하고 지금 실행"** 버튼 하나로 둘 다 처리하도록 만들었습니다.

토큰 없이 쓰려면 **"📋 YAML 복사"** 후 **"✏️ GitHub에서 직접 편집"**으로 붙여넣고,
Actions 탭에서 워크플로를 수동 실행하세요.
⚠ 토큰은 브라우저(localStorage)에만 저장됩니다. 공용 PC에서는 입력하지 마세요.

## 6. 과거 데이터 백필 (한 번에 채워넣기)

기준선 이전의 과거 거래를 차트에 채우고 싶을 때:

- **GitHub에서**: Actions 탭 → **"과거 데이터 백필"** → Run workflow → 개월 수 입력(예: 24) → Run
- **로컬에서**: `python monitor.py --backfill 24`

백필은 알림 없이 기록만 추가하며, 여러 번 실행해도 중복 저장되지 않습니다.

## 7. 네이버페이 부동산 호가(매물) 추적

매매(체결가)와 별개로 **현재 시장에 나온 매물의 호가**를 같은 시스템에 누적하고
대시보드 **🏷️ 호가** 탭에서 봅니다. 중복 제거, 동일 물건의 호가 변동 이력,
신규/내려간 매물 감지가 자동 적용됩니다.

> ⚠ **중요한 한계 2가지**
> - 호가는 **공식 API가 없어** 네이버페이 부동산의 비공식 API를 사용합니다(ToS 회색지대).
>   과도한 호출은 차단될 수 있어 **하루 1회 수준**으로만 쓰세요.
> - 호가는 **과거 조회(백필)가 불가능**합니다. "지금 이 순간"의 매물만 받을 수 있어,
>   **수집을 시작한 날부터** 스냅샷이 쌓입니다. 그래서 클라우드(GitHub Actions)가 아니라
>   **내 컴퓨터(로그인된 브라우저 세션)** 에서 수집합니다.

### 7-1. 단지번호(naver_id) 설정

각 단지에 네이버 단지번호를 넣으면 호가를 수집합니다(없으면 그 단지는 매매만):

```bash
python naver_lookup.py 이매촌삼성      # → naver_id: 2493
```

`config.yaml`의 해당 단지에 `naver_id: "2493"` 을 추가합니다(이미 예시 3개는 채워져 있음).

비공식 API라 **로그인 세션**이 필요하고, 네이버가 TLS 지문으로 봇을 막습니다.
두 가지 수집 방식이 있습니다 — **방식 A(Playwright)를 권장**합니다.

### 7-2. 방식 A — Playwright 자동 로그인 (권장, 토큰 입력 0회)

진짜 크로미움을 코드로 띄워 페이지가 발급한 토큰을 자동으로 받아 쓰므로,
**매번 토큰을 넣을 필요가 없습니다.** 한 번 설치하면 끝입니다.

```bash
pip install playwright
python -m playwright install chromium     # 최초 1회, 브라우저 다운로드(~150MB)

python quotes_monitor.py                  # 호가 수집 (토큰 입력 불필요!)
python quotes_monitor.py --headful        # 브라우저 창을 보면서 실행(디버그)
```

- 보통 **로그인 없이도** 매물 조회가 됩니다(매물 목록은 공개). 만약 토큰/조회 실패가 뜨면
  로그인을 1회 해두세요(프로필 `.naver_profile`에 저장돼 이후 자동 사용):
  ```bash
  python naver_playwright.py login          # 브라우저가 열리면 네이버 로그인 후 터미널에서 Enter
  ```
- 토큰 만료를 신경 쓸 필요가 없어 **launchd/cron으로 매일 자동 실행**도 가능합니다.

### 7-3. 방식 B — cURL 붙여넣기 (대안, 설치 최소)

Playwright 설치가 부담되면 `curl_cffi`만으로도 됩니다(토큰은 약 3시간마다 갱신):

```bash
pip install curl_cffi
```

1. 크롬에서 네이버 로그인 → `https://new.land.naver.com/complexes/2493` 접속
2. **F12 → Network 탭** → 필터 `article` → 매물이 보이게 스크롤
3. **`articles`** 요청 우클릭 → **Copy → Copy as cURL**
4. 복사한 내용을 프로젝트 폴더의 **`naver_curl.txt`** 에 통째로 붙여넣고 저장(`.gitignore`됨)
5. `python quotes_monitor.py --curl` 실행

> 방식 B의 토큰은 약 3시간 뒤 만료됩니다 → 호가를 새로 받을 때 cURL을 한 번 다시 떠서
> `naver_curl.txt`를 갱신하세요(약 30초). 만료되면 스크립트가 알려주고 기존 데이터는 **보존**합니다.

### 7-4. 호가 수집 실행

```bash
python quotes_monitor.py            # (방식 A) 수집 → 중복제거/변동감지 → 저장 → 대시보드
python quotes_monitor.py --curl     # (방식 B) cURL 세션으로 수집
python quotes_monitor.py --dry-run  # 저장 없이 감지 결과만
```

- 처음 실행은 기준선으로 저장만 합니다. 이후 실행부터 신규/인하/소멸을 감지·알림(텔레그램 선택)합니다.
- 결과는 `quotes_state.json`에 누적되고 대시보드 **🏷️ 호가** 탭에 표시됩니다.
- **세션 만료·차단 방어**: 매물이 갑자기 0건이거나 급감하면 기존 데이터를 지우지 않고
  경고만 띄웁니다(세션을 갱신하고 다시 실행).
- 데이터를 웹 대시보드에도 반영하려면 `git add quotes_state.json docs/index.html && git commit && git push`.

### 호가 탭 구성

- **요약 카드**: 단지·평형별 현재 최저호가 + 활성 매물 수 + **최근 실거래가 대비 갭**
- **호가 추이 차트**: 일별 최저/평균 호가 추이 + 실거래(체결) 오버레이
- **현재 호가**: 동일 세대를 묶어 대표(최저가) 1행 + 중개사별 펼침, 신규/인하/재등록 배지
- **변동·소멸 이력**: 같은 매물의 가격 인하/인상, 내려간 매물

## 파일 구조

```
monitor.py         # 매매: 조회 → 신규 감지 → 텔레그램 알림 → state/대시보드 갱신
quotes_monitor.py  # 호가: 네이버 매물 수집 → 중복제거/변동감지 → quotes_state/대시보드
quotes.py          # 호가 순수 도메인 로직 (식별·중복제거·변동/신규/소멸 감지)
naver_playwright.py # 호가 수집 방식 A: Playwright 자동 로그인(토큰 입력 0회, 권장)
naver_adapter.py   # 호가 수집 방식 B: cURL 토큰 세션(curl_cffi)
dashboard.py       # state+quotes → docs/index.html (현재 config 단지만 표시)
matching.py        # 관심단지 매칭 로직 (매매·호가·dashboard 공유)
lawd.py            # 시군구명 → 법정동코드 변환
search.py          # 실제 단지명·전용면적 조회 헬퍼 (config 작성용)
naver_lookup.py    # 네이버 단지번호(naver_id) 찾기
sgg_codes.json     # 전국 시군구 법정동코드 매핑 (code.go.kr 기준)
config.yaml        # 관심 단지 설정 (naver_id로 호가 대상 지정)
state.json         # 매매 거래 기록 (자동 생성·커밋)
quotes_state.json  # 호가 매물 기록 (로컬 수집·커밋)
docs/index.html    # 대시보드 (자동 생성·커밋)
```

## 참고: API 명세 (기술문서 기준)

- 엔드포인트: `https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev`
- 요청: `serviceKey`, `LAWD_CD`(법정동코드 5자리), `DEAL_YMD`(YYYYMM), `pageNo`, `numOfRows`
- 응답(XML): `aptNm` 단지명, `excluUseAr` 전용면적, `floor` 층, `dealAmount` 거래금액(만원),
  `dealYear/Month/Day` 계약일, `cdealType` 해제여부(`O`=해제), `dealingGbn` 거래유형 등
- 데이터 갱신주기: 일 1회 / ⚠ data.go.kr는 기본 curl/스크립트 User-Agent를 차단하므로 브라우저 UA로 호출
