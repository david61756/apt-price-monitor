#!/usr/bin/env python3
"""네이버페이 부동산 단지번호(naver_id) 찾기.

m.land 검색이 단지 상세(/complex/info/{번호})로 302 리다이렉트하는 점을 이용 — 비로그인으로 동작.

사용법:
    python naver_lookup.py 이매촌삼성
    python naver_lookup.py "신정마을 7단지"
"""
import sys
import urllib.parse

import requests

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def lookup(keyword):
    """방식1: m.land 검색이 단지 상세로 302 리다이렉트하는 것을 이용(비로그인, 빠름).

    단, 후보가 여러 개면 리다이렉트가 안 걸려 실패한다 → 그때는 search_api()로 넘어간다.
    """
    enc = urllib.parse.quote(keyword)
    r = requests.get(f"https://m.land.naver.com/search/result/{enc}",
                     headers={"user-agent": UA}, allow_redirects=False, timeout=20)
    loc = r.headers.get("location", "")
    if "/complex/info/" in loc:
        return loc.split("/complex/info/")[1].split("?")[0]
    return None


def search_api(keyword, limit=8):
    """방식2: new.land 검색 API를 브라우저(Playwright) 안에서 호출해 후보 목록을 받는다.

    리다이렉트가 안 되는 이름(동명 단지가 여럿이거나 부분일치가 애매한 경우)도 찾아준다.
    반환: [(단지명, 단지번호, 주소), ...]
    """
    import naver_playwright
    from playwright.sync_api import sync_playwright
    js = """async (q) => {
        const r = await fetch('/api/search?keyword=' + encodeURIComponent(q) + '&page=1',
                              {headers: {accept: '*/*'}});
        if (!r.ok) return null;
        return await r.json();
    }"""
    with sync_playwright() as p:
        ctx = naver_playwright._new_context(p, True)
        page = ctx.new_page()
        try:
            page.goto("https://new.land.naver.com/complexes",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            body = page.evaluate(js, keyword) or {}
        finally:
            ctx.close()
    out = []
    for c in (body.get("complexes") or body.get("complexList") or [])[:limit]:
        out.append((c.get("complexName"), str(c.get("complexNo")),
                    c.get("cortarAddress") or c.get("address") or ""))
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python naver_lookup.py <단지명>")
    kw = " ".join(sys.argv[1:])
    no = lookup(kw)
    if no:
        print(f"'{kw}' → naver_id: {no}")
        print(f"  확인: https://new.land.naver.com/complexes/{no}")
        return
    # 리다이렉트 실패 → 검색 API로 후보 조회(동명 단지가 많은 경우)
    print(f"'{kw}' 직접 매칭 실패 → 검색 API로 후보를 찾는 중...")
    try:
        cands = search_api(kw)
    except Exception as e:
        sys.exit(f"검색 API 실패: {e}\n  (playwright 미설치면: python3 -m playwright install chromium)")
    if not cands:
        print(f"'{kw}' 후보 없음. 단지명을 더 정확히 쓰거나 지역명을 붙여 보세요.")
        return
    print(f"후보 {len(cands)}개:")
    for nm, no, addr in cands:
        print(f"  naver_id: {no:>8s}  {nm}  ({addr})")


if __name__ == "__main__":
    main()
