"""네이버 호가(매물) 데이터 — 순수 도메인 로직 (네트워크 의존 없음).

핵심 설계 (설계 워크플로 합의안):
- 식별 2계층: article_no(이력의 원자 키) + unit_key(표시용 동일세대 묶음 키).
  가격 변동 이력(price_history)은 '항상' article_no 단위로만 남긴다 → 잘못 묶여도 이력 오염 없음.
- unit_key는 동·해당층·향이 하나라도 비면 confident=False → 묶지 않고 단독 처리(오합침 방지).
- GONE(매물 내려감)은 '수집 성공 단지' 범위 안에서 '연속 N회 미관측'일 때만(세션만료·결손 방어).
- 가격은 매매와 동일하게 만원(int). apt_nm/area/lawd_cd 필드명을 매매와 일치시켜 match_complex·groupKey 재사용.
"""
import json
import re
from pathlib import Path

GONE_THRESHOLD = 2          # 연속 미관측 N회 이상이면 gone
RELIST_PRICE_TOL = 0.10     # 재등록 추정 시 허용 가격 오차(±10%)
DROP_GUARD = 0.20           # 전체 수집 수가 직전 active의 이 비율 미만이면 '차단 의심'

BASE_DIR = Path(__file__).resolve().parent
QUOTES_PATH = BASE_DIR / "quotes_state.json"


# ----------------------------------------------------------------- 파싱/정규화

def parse_price(s):
    """'13억 2,000' -> 132000, '8억' -> 80000, '5,000' -> 5000 (만원). 실패 시 None."""
    if not s:
        return None
    s = str(s).replace(" ", "")
    eok = 0
    if "억" in s:
        head, _, s = s.partition("억")
        head = head.replace(",", "")
        eok = int(head) if head.isdigit() else 0
    man_str = s.replace(",", "")
    man = int(man_str) if man_str.isdigit() else 0
    total = eok * 10000 + man
    return total if total > 0 else None


def norm_building(s):
    """'제101동' / '101동' / '101' -> '101'. 없으면 '?'."""
    digits = re.sub(r"\D", "", s or "")
    return digits or "?"


def norm_direction(s):
    """'남동향' -> '남동'. 없으면 ''."""
    return (s or "").replace("향", "").strip()


def make_unit_key(rec):
    """(unit_key, confident). 동·해당층·향이 모두 있어야 confident=True."""
    floor = rec.get("floor_self") or ""
    dong = rec.get("building_name") or "?"
    direction = rec.get("direction") or ""
    confident = bool(floor) and dong not in ("", "?") and bool(direction)
    key = "|".join([
        str(rec.get("lawd_cd", "")), rec.get("complex", ""), rec.get("trade_code", ""),
        dong, str(floor), f"{round(float(rec.get('area') or 0), 1)}", direction,
    ])
    return key, confident


def parse_article(raw, complex_name, lawd_cd):
    """네이버 article(raw dict) -> 내부 호가 레코드. 가격 파싱 실패 시 None."""
    price = parse_price(raw.get("dealOrWarrantPrc"))
    if price is None:
        return None
    floor_info = raw.get("floorInfo") or ""
    floor_self, _, floor_total = floor_info.partition("/")
    rec = {
        "article_no": str(raw.get("articleNo") or "").strip(),
        "complex": complex_name,
        "apt_nm": (raw.get("articleName") or "").strip(),
        "lawd_cd": str(lawd_cd),
        "trade_type": raw.get("tradeTypeName") or "",
        "trade_code": raw.get("tradeTypeCode") or "",
        "area_supply": _f(raw.get("area1")),
        "area": _f(raw.get("area2")),       # 전용㎡ (매매 area와 동일 의미)
        "area_name": raw.get("areaName") or "",
        "floor_self": floor_self.strip(),
        "floor_total": floor_total.strip(),
        "direction": norm_direction(raw.get("direction")),
        "building_name": norm_building(raw.get("buildingName")),
        "price": price,
        "price_raw": (raw.get("dealOrWarrantPrc") or "").strip(),
        "rent_man": parse_price(raw.get("rentPrc")) or 0,
        "realtor": raw.get("realtorName") or "",
        "cp_name": raw.get("cpName") or "",
        "feature": (raw.get("articleFeatureDesc") or "").strip(),
        "confirm_ymd": raw.get("articleConfirmYmd") or "",
        "same_addr_cnt": int(raw.get("sameAddrCnt") or 1),
    }
    if not rec["article_no"]:
        return None
    rec["unit_key"], rec["unit_key_confident"] = make_unit_key(rec)
    return rec


def _f(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------- reconcile

def guess_relist(rec, quotes):
    """같은 unit_key로 최근 존재했던 다른 article_no(재등록 추정). 병합은 안 하고 태그만."""
    if not rec.get("unit_key_confident"):
        return None
    for an, q in quotes.items():
        if (q.get("unit_key") == rec["unit_key"]
                and q.get("article_no") != rec["article_no"]
                and q.get("status") in ("gone", "active")
                and abs(q["price"] - rec["price"]) <= q["price"] * RELIST_PRICE_TOL):
            return an
    return None


_META_FIELDS = ("floor_self", "floor_total", "direction", "building_name", "area",
                "area_supply", "area_name", "feature", "confirm_ymd", "same_addr_cnt",
                "realtor", "cp_name", "unit_key", "unit_key_confident", "price_raw")


def merge_meta(prev, rec):
    """가격/이력 외 메타데이터를 최신 관측값으로 갱신."""
    for f in _META_FIELDS:
        if f in rec:
            prev[f] = rec[f]


def reconcile(qstate, fetched_by_complex, scanned_complexes, now):
    """스냅샷을 기존 state에 반영.

    fetched_by_complex: {complex_name: [parsed_rec, ...]}  (이미 파싱·면적필터됨)
    scanned_complexes:  set(이번에 조회 성공한 complex_name)
    반환: (quotes 또는 None, events). None이면 '차단 의심'으로 호출부가 저장을 건너뛴다.
    events: (kind, ...) 리스트. kind ∈ NEW/PRICE_DOWN/PRICE_UP/GONE/RELIST/EMPTY_SUSPECT/BLOCKED_SUSPECT
    """
    quotes = qstate.setdefault("quotes", {})
    iso = now.isoformat(timespec="seconds")
    today = now.strftime("%Y-%m-%d")
    events = []
    seen = set()

    total_fetched = sum(len(v) for v in fetched_by_complex.values())
    prev_active = sum(1 for q in quotes.values() if q.get("status") == "active")

    # (E-3) 전역 차단 가드: 직전 active가 있는데 전체 수집이 급감 → 저장 스킵
    if prev_active and total_fetched < prev_active * DROP_GUARD:
        return None, [("BLOCKED_SUSPECT", prev_active, total_fetched)]

    scanned = set(scanned_complexes)
    for complex_name, recs in fetched_by_complex.items():
        # (E-2) 직전 active≥1인데 이번 0건 → 세션만료 의심, 이 단지 GONE 판정 스킵
        had_active = any(q.get("complex") == complex_name and q.get("status") == "active"
                         for q in quotes.values())
        if had_active and not recs:
            scanned.discard(complex_name)
            events.append(("EMPTY_SUSPECT", complex_name))
            continue

        for rec in recs:
            an = rec["article_no"]
            seen.add(an)
            prev = quotes.get(an)
            if prev is None:                         # ── 신규 매물
                rec.update(
                    status="active", miss_count=0, relisted_count=0,
                    relist_of=guess_relist(rec, quotes),
                    first_seen=iso, last_seen=iso, gone_date=None,
                    price_history=[{"date": today, "price": rec["price"]}],
                )
                quotes[an] = rec
                events.append(("NEW", rec))
            else:                                    # ── 기존 매물
                prev["last_seen"] = iso
                prev["miss_count"] = 0
                if prev.get("status") == "gone":     # 재등장
                    prev["status"] = "active"
                    prev["gone_date"] = None
                    prev["relisted_count"] = prev.get("relisted_count", 0) + 1
                    events.append(("RELIST", prev))
                if rec["price"] != prev["price"]:    # 같은 article의 가격 변동만 이력화
                    old = prev["price"]
                    prev["price_history"].append({"date": today, "price": rec["price"]})
                    prev["price"] = rec["price"]
                    events.append(("PRICE_DOWN" if rec["price"] < old else "PRICE_UP", prev, old))
                merge_meta(prev, rec)

    # ── GONE: 수집 성공 단지 한정, 연속 미관측 N회 이상
    for an, q in quotes.items():
        if q.get("status") != "active":
            continue
        if q.get("complex") not in scanned:
            continue
        if an in seen:
            continue
        q["miss_count"] = q.get("miss_count", 0) + 1
        if q["miss_count"] >= GONE_THRESHOLD:
            q["status"] = "gone"
            q["gone_date"] = today
            events.append(("GONE", q))

    # collected 메타 (조회 성공 단지만)
    collected = qstate.setdefault("collected", {})
    for cn in scanned:
        active = sum(1 for q in quotes.values()
                     if q.get("complex") == cn and q.get("status") == "active")
        collected[cn] = {"last_ok": iso, "active_cnt": active}

    qstate.setdefault("tracking_since", today)
    qstate["last_run"] = iso
    return quotes, events


def quote_in_config(q, complexes):
    """호가가 현재 config의 어떤 관심단지에 속하는지(있으면 그 이름).

    호가는 naver_id로 수집 시 단지를 특정해 complex 이름을 박아두므로,
    단지명 텍스트 매칭(매매와 네이버 등록명이 다름)이 아니라
    '그 complex 이름이 아직 config에 있고 + 전용면적이 areas에 맞는가'로 판정한다.
    """
    for c in complexes:
        if q.get("complex") == c["name"]:
            if not c["areas"] or int(float(q.get("area") or 0)) in c["areas"]:
                return c["name"]
    return None


def prune_quotes(quotes, complexes):
    """관심단지에서 빠졌거나 면적이 안 맞는 매물 제거 — 매매 prune과 동형."""
    return {an: q for an, q in quotes.items()
            if quote_in_config(q, complexes) is not None}


# --------------------------------------------------------------------- state IO

def load_quotes_state(path=QUOTES_PATH):
    path = Path(path)
    if not path.exists():
        return {"schema": 1, "quotes": {}, "collected": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_quotes_state(qstate, path=QUOTES_PATH):
    Path(path).write_text(
        json.dumps(qstate, ensure_ascii=False, indent=1), encoding="utf-8")
