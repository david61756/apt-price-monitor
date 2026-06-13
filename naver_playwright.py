"""Playwright 기반 네이버 호가 수집 — 토큰 수동 입력 불필요.

진짜 크로미움(영속 프로필 .naver_profile)으로 단지 페이지를 열면 페이지 JS가
Authorization 토큰을 자동 발급한다. 그 토큰을 가로채 '페이지 내부 fetch'로 매물 API를
페이지네이션하면, 실제 브라우저 컨텍스트라 TLS/anti-bot을 통과하고 깨끗한 JSON을 그대로 받는다.

사용:
    python naver_playwright.py            # 전 단지 호가 조회(테스트 출력)
    python naver_playwright.py login      # 네이버 로그인 1회(보통 불필요 — 매물은 비로그인 조회 가능)
보통은 quotes_monitor.py가 이 모듈을 호출한다.
"""
from pathlib import Path

from naver_adapter import DEFAULT_UA, MAX_PAGES, _article_params
from quotes import parse_article

BASE = Path(__file__).resolve().parent
PROFILE_DIR = BASE / ".naver_profile"

_INPAGE_FETCH = """async ({nid, token, params}) => {
  const qs = new URLSearchParams(params).toString();
  const r = await fetch(`/api/articles/complex/${nid}?` + qs,
                        {headers: {authorization: token, accept: '*/*'}});
  if (!r.ok) return {status: r.status};
  return {status: 200, body: await r.json()};
}"""


def _new_context(p, headless):
    return p.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=headless, user_agent=DEFAULT_UA,
        locale="ko-KR", viewport={"width": 1280, "height": 900})


def _capture_token(page, nid):
    """단지 페이지를 열어 페이지가 발급한 Authorization 토큰을 가로챈다."""
    box = {"auth": None}

    def on_req(req):
        if f"/api/articles/complex/{nid}" in req.url and not box["auth"]:
            box["auth"] = req.headers.get("authorization")

    page.on("request", on_req)
    try:
        page.goto(f"https://new.land.naver.com/complexes/{nid}",
                  wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass
    for _ in range(48):                       # 최대 ~12초 대기
        if box["auth"]:
            break
        page.wait_for_timeout(250)
    return box["auth"]


def _fetch_articles_inpage(page, nid, trade_types):
    """페이지 내부 fetch로 매물 목록 페이지네이션. (raw articles, ok)."""
    articles, ok = [], True
    token = _capture_token(page, nid)
    if not token:
        return [], False
    for tt in trade_types:
        for pg in range(1, MAX_PAGES + 1):
            params = {k: str(v) for k, v in _article_params(nid, tt, pg).items()}
            res = page.evaluate(_INPAGE_FETCH, {"nid": nid, "token": token, "params": params})
            if res.get("status") != 200:
                ok = False
                break
            body = res.get("body") or {}
            if "articleList" not in body:
                ok = False
                break
            articles.extend(body.get("articleList") or [])
            if not body.get("isMoreData"):
                break
            page.wait_for_timeout(400)
    return articles, ok


def fetch_all_playwright(cfg, headless=True, log=print):
    """관심단지(naver_id)별 호가 수집. 반환 (fetched_by_complex, scanned) — 어댑터와 동일 형태."""
    from playwright.sync_api import sync_playwright

    naver = cfg.get("naver") or {}
    trade_types = naver.get("trade_types") or ["A1"]
    fetched, scanned = {}, set()
    with sync_playwright() as p:
        ctx = _new_context(p, headless)
        try:
            for c in cfg["complexes"]:
                nid = c.get("naver_id")
                if not nid:
                    continue
                log(f"호가 조회(PW): {c['name']} (naver_id={nid}) ...")
                page = ctx.new_page()
                raws, ok = _fetch_articles_inpage(page, str(nid), trade_types)
                page.close()
                if not raws and not ok:
                    log("    ! 토큰/조회 실패 — 로그인이 필요하면: python naver_playwright.py login")
                recs = []
                for raw in raws:
                    r = parse_article(raw, c["name"], c["lawd_cd"])
                    if r and (not c["areas"] or int(r["area"]) in c["areas"]):
                        recs.append(r)
                fetched[c["name"]] = recs
                if ok:
                    scanned.add(c["name"])
                log(f"    매물 {len(raws)}건 중 관심조건 매칭 {len(recs)}건"
                    + ("" if ok else "  ⚠ 조회 불완전 — GONE 판정 제외"))
        finally:
            ctx.close()
    return fetched, scanned


def login(log=print):
    """헤드풀 브라우저로 네이버 로그인 1회. 프로필(.naver_profile)에 저장돼 이후 자동 사용."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _new_context(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://nid.naver.com/nidlogin.login")
        log("열린 브라우저에서 네이버 로그인을 마친 뒤, 이 터미널에서 Enter를 누르세요...")
        try:
            input()
        except EOFError:
            page.wait_for_timeout(90000)
        ctx.close()
        log("✅ 로그인 프로필 저장 완료. 이제 토큰 입력 없이 자동 수집됩니다.")


if __name__ == "__main__":
    import sys
    import monitor
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login()
    else:
        monitor.load_env()
        cfg = monitor.load_config()
        fetched, scanned = fetch_all_playwright(cfg, headless=True)
        print("\n수집 결과:", {k: len(v) for k, v in fetched.items()}, "| scanned:", scanned)
