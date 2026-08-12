전역 작업/행동 원칙은 ~/.claude/CLAUDE.md 참조 (중복 금지)

## 목적
국토부 실거래가 API + 네이버페이 부동산 호가를 매일 수집해 관심 단지 변동을 Discord 알림하고 `docs/index.html` 대시보드를 자동 갱신하는 파이프라인.

## 실행
venv 없음. 스크립트는 시스템 `python3`(= /opt/anaconda3/bin, 셸 스크립트가 PATH 선두로 설정) 사용.
- `python3 update.py` — 실거래+호가 통합 갱신 → 변동 요약 Discord (`--no-notify`). launchd가 호출하는 메인.
- `python3 monitor.py` — 매매만. `--dry-run`(감지만) / `--no-notify` / `--backfill N`(N개월 과거 채움, 알림 없음)
- `python3 quotes_monitor.py` — 호가만. `--dry-run` / `--no-notify` / `--curl`(방식B) / `--headful`(브라우저 창)
- `python3 search.py "경기도 용인시 수지구" [키워드]` — config용 실제 단지명·전용면적 조회
- `python3 naver_lookup.py 이매촌삼성` — 단지의 naver_id 조회
- `python3 order_server.py` — 로컬 대시보드 서버 :8787 + 카드 순서 자동 저장 (또는 `대시보드_열기.command` 더블클릭)
- 호가 방식A(권장) 최초 1회: `python3 -m playwright install chromium`, 필요 시 `python3 naver_playwright.py login`

## 구조
- `update.py` / `monitor.py` / `quotes_monitor.py` — 실거래+호가 통합 / 매매 / 호가 진입점
- `quotes.py` — 호가 순수 도메인 로직(식별·중복제거·NEW/PRICE_DOWN/GONE 감지). test 대상
- `naver_playwright.py`(방식A, Playwright 자동로그인) / `naver_adapter.py`(방식B, curl_cffi 토큰)
- `dashboard.py` — state+quotes → `docs/index.html` (현재 config 단지만 표시)
- `matching.py`(단지 매칭 공유) / `lawd.py`(시군구명→법정동코드) / `sgg_codes.json`(전국 매핑)
- `config.yaml` — 관심 단지(match/areas/naver_id) + `targets`(면적대별 목표가, 도달 시 🎯 알림·강조)
  · `watch`(관심 매물번호 목록, 📌 개별 추적). 매물번호는 대시보드 호가 목록의 펼침 행에 `#번호`로 표시된다.
  `state.json`(매매)·`quotes_state.json`(호가) 자동 생성·커밋
- `run_quotes.sh`(수집→커밋→푸시) / `sync_quotes.sh`(원격 config 변경 시 호가 동기화) — launchd가 호출

## 테스트
`python3 test_quotes.py` — quotes.py 순수 로직을 네트워크 없이 검증(가격 파싱·재등록·차단 가드 등).

## 스케줄러 / 주의·함정
- LaunchAgent 2개: `com.aptmonitor.quotes`(run_quotes.sh, **매일 08:00/14:00/18:00 KST**) / `com.aptmonitor.sync`(sync_quotes.sh, **900초=15분 주기**로 원격 config 변경 감지 시에만 호가 동기화). 확인: `launchctl list | grep aptmonitor`.
  ※ README 7-5의 "오전 9:10" 표기는 stale — 실제는 위 plist 기준.
- 매매(monitor)는 GitHub Actions(클라우드 백업, `.github/workflows/monitor.yml` cron 23/05/09 UTC = 08/14/18 KST)도 돌지만, **호가(quotes)는 로그인 세션이 필요해 로컬 Mac에서만** 수집.
- `naver.trade_types`에 `B1`(전세)을 넣으면 전세 호가도 수집된다. 대시보드는 `SALE_Q`/`JEONSE_Q`로
  **매매·전세를 분리**해 쓴다(최저호가·차트·수급은 매매만, 전세는 전세가율 계산에만 사용).
- 카드 지표는 모두 **단지×면적대** 단위로 계산한다(단지 단위로 묶으면 다른 평형 가격이 섞여 갭·최저호가가 왜곡됨).
- 호가는 **네이버 비공식 API**(ToS 회색지대) — 하루 1회 수준으로만. **과거 백필 불가**(수집 시작일부터 스냅샷만 축적). 로그인 세션은 `.naver_profile`에 저장. 방식B는 `naver_curl.txt` 토큰이 ~3시간 만료.
- 세션만료/차단 방어: 전체 0건이면 `BLOCKED_SUSPECT`로 저장 스킵(기존 보존), 부분 0건은 `EMPTY_SUSPECT`로 해당 단지 GONE 판정만 스킵. GONE은 연속 2회 미관측(2일 디바운스) 후 확정.
- `config.yaml`의 `match`는 **실제 등록 단지명과 정확 일치** 필요(예: `이매촌(삼성)` — 괄호까지). `areas`는 실제 존재하는 전용면적 정수.
- data.go.kr는 기본 curl/스크립트 User-Agent 차단 → 코드가 브라우저 UA로 호출.
- git push 인증은 `.env`의 `GITHUB_TOKEN`을 extraheader로 주입(리모트 URL/.git/config에 토큰 안 남김). 키: `.env`(MOLIT_API_KEY, DISCORD_WEBHOOK_URL, GITHUB_TOKEN, NAVER_AUTH/COOKIE).
- run_quotes ↔ sync_quotes 는 `logs/.run.lock` 으로 상호배제(동일 .naver_profile/Chromium·push 경쟁 방지).
