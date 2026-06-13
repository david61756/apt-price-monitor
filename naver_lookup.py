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
    enc = urllib.parse.quote(keyword)
    r = requests.get(f"https://m.land.naver.com/search/result/{enc}",
                     headers={"user-agent": UA}, allow_redirects=False, timeout=20)
    loc = r.headers.get("location", "")
    if "/complex/info/" in loc:
        return loc.split("/complex/info/")[1].split("?")[0]
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python naver_lookup.py <단지명>")
    kw = " ".join(sys.argv[1:])
    no = lookup(kw)
    if no:
        print(f"'{kw}' → naver_id: {no}")
        print(f"  확인: https://new.land.naver.com/complexes/{no}")
    else:
        print(f"'{kw}' 단지번호를 못 찾았습니다. 검색어를 바꿔 보세요(예: '신정마을7단지').")


if __name__ == "__main__":
    main()
