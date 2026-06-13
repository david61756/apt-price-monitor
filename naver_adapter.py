"""네이버페이 부동산 매물(호가) 수집 어댑터.

수집은 '사용자의 로그인된 브라우저 세션'을 빌려서 한다(공식 API 아님, 비공식 내부 API).
세션 = .env의 NAVER_AUTH(Authorization Bearer 토큰) + NAVER_COOKIE(쿠키 문자열).
둘 다 로그인된 네이버페이 부동산에서 개발자도구 Network의 매물목록 요청에서 복사한다(README 참고).

⚠ data.go.kr 매매와 달리 호가는 공개 API가 없어 anti-bot이 강하다. GitHub Actions(클라우드 IP)는
   차단되므로 이 어댑터는 '로컬(가정용 IP) + 로그인 세션'에서 실행하는 것을 전제로 한다.
"""
import time

import requests

from matching import match_complex
from quotes import parse_article

# 단지별 매물 목록 (new.land REST). 페이지가 fin.land로 보여도 백엔드 API는 이 경로를 쓴다.
ARTICLES_URL = "https://new.land.naver.com/api/articles/complex/{complex_no}"

TRADE_NAME = {"A1": "매매", "B1": "전세", "B2": "월세"}
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MAX_PAGES = 30          # 단지·거래유형당 안전 상한 (1page=20건)
REQUEST_GAP = 0.7       # 요청 간 간격(초) — 예의상 저속


def build_session():
    """.env/환경변수에서 네이버 세션 헤더 구성. 없으면 (None, 사유)."""
    import os
    auth = os.environ.get("NAVER_AUTH", "").strip()
    cookie = os.environ.get("NAVER_COOKIE", "").strip()
    if not auth:
        return None, "NAVER_AUTH(Authorization Bearer 토큰)가 .env에 없습니다."
    if not auth.lower().startswith("bearer"):
        auth = "Bearer " + auth
    headers = {
        "authorization": auth,
        "user-agent": os.environ.get("NAVER_UA", DEFAULT_UA),
        "accept": "*/*",
        "accept-language": "ko-KR,ko;q=0.9",
    }
    if cookie:
        headers["cookie"] = cookie
    return headers, None


def _article_params(complex_no, trade_type, page):
    return {
        "realEstateType": "APT:PRE:ABYG:JGC",
        "tradeType": trade_type,
        "tag": "::::::::",
        "rentPriceMin": 0, "rentPriceMax": 900000000,
        "priceMin": 0, "priceMax": 900000000,
        "areaMin": 0, "areaMax": 900000000,
        "showArticle": "false",
        "sameAddressGroup": "false",     # 동일주소 묶지 않고 개별 매물 전부 수신
        "priceType": "RETAIL",
        "page": page,
        "complexNo": complex_no,
        "type": "list",
        "order": "rank",
    }


def fetch_articles(complex_no, trade_types, session, log=print):
    """한 단지의 매물 원본(raw dict) 목록. (articles, ok). ok=False면 그 단지는 신뢰 불가."""
    articles, ok = [], True
    for tt in trade_types:
        for page in range(1, MAX_PAGES + 1):
            url = ARTICLES_URL.format(complex_no=complex_no)
            params = _article_params(complex_no, tt, page)
            headers = dict(session, referer=f"https://new.land.naver.com/complexes/{complex_no}")
            try:
                r = requests.get(url, params=params, headers=headers, timeout=20)
            except requests.RequestException as e:
                log(f"    ! 요청 실패({e})")
                ok = False
                break
            if r.status_code in (401, 403):
                log(f"    ! 인증 실패({r.status_code}) — 세션(NAVER_AUTH/NAVER_COOKIE) 만료 의심")
                ok = False
                break
            if r.status_code == 429:
                log("    ! 429 Rate limit — 잠시 대기 후 재시도")
                time.sleep(3)
                ok = False
                break
            if not r.ok:
                log(f"    ! HTTP {r.status_code}")
                ok = False
                break
            try:
                data = r.json()
            except ValueError:
                log("    ! JSON 파싱 실패")
                ok = False
                break
            if "articleList" not in data:
                log("    ! 응답에 articleList 없음 (세션/엔드포인트 확인 필요)")
                ok = False
                break
            articles.extend(data.get("articleList") or [])
            if not data.get("isMoreData"):
                break
            time.sleep(REQUEST_GAP)
    return articles, ok


def fetch_all(cfg, session, log=print):
    """관심단지(naver_id 보유)별 매물 수집·파싱·면적필터.

    반환: (fetched_by_complex {name:[rec,...]}, scanned_complexes set)
    scanned = 조회에 성공한(신뢰 가능한) 단지만 → reconcile의 GONE 판정 대상.
    """
    naver_cfg = cfg.get("naver") or {}
    trade_types = naver_cfg.get("trade_types") or ["A1"]
    fetched, scanned = {}, set()
    for c in cfg["complexes"]:
        nid = c.get("naver_id")
        if not nid:
            continue
        log(f"호가 조회: {c['name']} (naver_id={nid}) ...")
        raws, ok = fetch_articles(str(nid), trade_types, session, log=log)
        recs = []
        for raw in raws:
            rec = parse_article(raw, c["name"], c["lawd_cd"])
            if rec and match_complex(rec, c):     # 전용면적(areas) 등 관심조건 필터
                recs.append(rec)
        fetched[c["name"]] = recs
        if ok:
            scanned.add(c["name"])
        log(f"    매물 {len(raws)}건 중 관심조건 매칭 {len(recs)}건"
            + ("" if ok else "  ⚠ 조회 불완전 — GONE 판정 제외"))
        time.sleep(REQUEST_GAP)
    return fetched, scanned
