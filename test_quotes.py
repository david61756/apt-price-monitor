"""quotes.py 순수 로직 검증 (네트워크 없이). 실행: python test_quotes.py"""
from datetime import datetime, timedelta, timezone

import quotes as q

KST = timezone(timedelta(hours=9))
COMPLEXES = [{
    "name": "이매촌삼성 전용73㎡(27평)", "lawd_cd": "41135",
    "match": ["이매촌(삼성)"], "areas": [73],
}]


def chk(name, cond):
    print(("✓" if cond else "✗ 실패:"), name)
    assert cond, name


# 1) 가격 파싱
chk("13억 2,000 -> 132000", q.parse_price("13억 2,000") == 132000)
chk("8억 -> 80000", q.parse_price("8억") == 80000)
chk("5,000 -> 5000", q.parse_price("5,000") == 5000)
chk("15억 -> 150000", q.parse_price("15억") == 150000)
chk("빈값 -> None", q.parse_price("") is None and q.parse_price(None) is None)

# 2) 정규화 / unit_key
chk("동 정규화", q.norm_building("제101동") == "101")
chk("향 정규화", q.norm_direction("남동향") == "남동")
r = {"lawd_cd": "41135", "complex": "C", "trade_code": "A1",
     "building_name": "102", "floor_self": "12", "area": 73.25, "direction": "남"}
k, conf = q.make_unit_key(r)
chk("unit_key confident", conf is True and f"{round(73.25, 1)}" in k)
r2 = dict(r, direction="")
_, conf2 = q.make_unit_key(r2)
chk("향 결측 -> not confident", conf2 is False)


def raw(article_no, price, floor="12", dong="102", direction="남향", area2="73.25"):
    return {"articleNo": article_no, "articleName": "이매촌(삼성)", "tradeTypeName": "매매",
            "tradeTypeCode": "A1", "dealOrWarrantPrc": price, "area1": "95.86", "area2": area2,
            "areaName": "29평", "floorInfo": f"{floor}/15", "direction": direction,
            "buildingName": dong, "articleConfirmYmd": "20260612", "sameAddrCnt": "1"}


def parse_filter(raws):
    out = []
    for rw in raws:
        rec = q.parse_article(rw, COMPLEXES[0]["name"], "41135")
        if rec and q.match_complex(rec, COMPLEXES[0]):
            out.append(rec)
    return out


t0 = datetime(2026, 6, 1, 20, tzinfo=KST)
st = {"schema": 1, "quotes": {}, "collected": {}}

# 3) 1회차: 신규 2건 (하나는 area 84로 필터링되어 빠져야 함)
snap1 = parse_filter([raw("A1", "13억 5,000"), raw("A2", "13억"),
                      raw("X", "20억", area2="84.9")])
chk("면적필터(84 제외)", len(snap1) == 2)
quotes, ev = q.reconcile(st, {COMPLEXES[0]["name"]: snap1}, {COMPLEXES[0]["name"]}, t0)
chk("1회차 신규 2건", sum(1 for e in ev if e[0] == "NEW") == 2)
chk("tracking_since 기록", st["tracking_since"] == "2026-06-01")

# 4) 2회차: A1 가격 인하, A2 유지, A3 신규
snap2 = parse_filter([raw("A1", "13억"), raw("A2", "13억"), raw("A3", "12억 8,000")])
quotes, ev = q.reconcile(st, {COMPLEXES[0]["name"]: snap2}, {COMPLEXES[0]["name"]},
                         t0 + timedelta(days=1))
kinds = [e[0] for e in ev]
chk("2회차 PRICE_DOWN 1건", kinds.count("PRICE_DOWN") == 1)
chk("2회차 NEW 1건(A3)", kinds.count("NEW") == 1)
chk("A1 가격이력 2건", len(quotes["A1"]["price_history"]) == 2 and quotes["A1"]["price"] == 130000)

# 5) 3·4회차: A2 사라짐 → 연속 2회 미관측 후 GONE
snap3 = parse_filter([raw("A1", "13억"), raw("A3", "12억 8,000")])
quotes, ev = q.reconcile(st, {COMPLEXES[0]["name"]: snap3}, {COMPLEXES[0]["name"]},
                         t0 + timedelta(days=2))
chk("3회차 아직 GONE 아님(miss=1)", quotes["A2"]["status"] == "active")
quotes, ev = q.reconcile(st, {COMPLEXES[0]["name"]: snap3}, {COMPLEXES[0]["name"]},
                         t0 + timedelta(days=3))
chk("4회차 GONE(miss=2)", quotes["A2"]["status"] == "gone"
    and ("GONE" in [e[0] for e in ev]))

# 7) prune: 관심단지에서 빠지면 제거
chk("prune 전부 제거", len(q.prune_quotes(quotes, [])) == 0)

# 6) 재등록 추정(standalone): D(다른 층)는 유지, A2(12층)는 내려갔다가 새 번호 A2b로 재등록
stR = {"schema": 1, "quotes": {}, "collected": {}}
cn = COMPLEXES[0]["name"]
def snap(arts):
    return {cn: parse_filter(arts)}
q.reconcile(stR, snap([raw("D", "9억", floor="5"), raw("A2", "13억", floor="12")]),
            {cn}, t0)                                    # 1회차: D, A2 active
q.reconcile(stR, snap([raw("D", "9억", floor="5")]), {cn}, t0 + timedelta(days=1))   # A2 miss=1
qR, _ = q.reconcile(stR, snap([raw("D", "9억", floor="5")]), {cn}, t0 + timedelta(days=2))  # A2 GONE
chk("standalone A2 GONE", qR["A2"]["status"] == "gone")
qR, evR = q.reconcile(stR, snap([raw("D", "9억", floor="5"),
                                 raw("A2b", "13억", floor="12")]), {cn}, t0 + timedelta(days=3))
chk("재등록 태그(relist_of=A2)", qR["A2b"].get("relist_of") == "A2")

# 8) 부분 0건 방어(EMPTY_SUSPECT): 2개 단지 중 한 곳만 0건 -> 그 단지 GONE 판정 스킵
cB = {"name": "B단지", "lawd_cd": "41135", "match": ["이매촌(삼성)"], "areas": [73]}
def pf(raws, cfg):
    out = []
    for rw in raws:
        rec = q.parse_article(rw, cfg["name"], cfg["lawd_cd"])
        if rec and q.match_complex(rec, cfg):
            out.append(rec)
    return out
st2 = {"schema": 1, "quotes": {}, "collected": {}}
both = {COMPLEXES[0]["name"]: pf([raw("A1", "13억"), raw("A2", "13억 5,000")], COMPLEXES[0]),
        cB["name"]: pf([raw("B1", "12억")], cB)}
q.reconcile(st2, both, {COMPLEXES[0]["name"], cB["name"]}, t0)
# 다음 회차: A는 정상, B는 0건
quotes2, ev2 = q.reconcile(
    st2, {COMPLEXES[0]["name"]: pf([raw("A1", "13억"), raw("A2", "13억 5,000")], COMPLEXES[0]),
          cB["name"]: []},
    {COMPLEXES[0]["name"], cB["name"]}, t0 + timedelta(days=1))
chk("부분 0건 -> EMPTY_SUSPECT", any(e[0] == "EMPTY_SUSPECT" for e in ev2))
chk("부분 0건 -> B 매물 보존(miss 안 올림)",
    quotes2["B1"]["status"] == "active" and quotes2["B1"]["miss_count"] == 0)

# 9) 전역 차단 가드: 직전 active 10건인데 이번 1건(<20%) -> BLOCKED_SUSPECT, 저장 None
stG = {"schema": 1, "quotes": {}, "collected": {}}
many = pf([raw(f"G{i}", "13억", floor=str(i)) for i in range(10)], COMPLEXES[0])
q.reconcile(stG, {COMPLEXES[0]["name"]: many}, {COMPLEXES[0]["name"]}, t0)
res, ev3 = q.reconcile(
    stG, {COMPLEXES[0]["name"]: pf([raw("G0", "13억", floor="0")], COMPLEXES[0])},
    {COMPLEXES[0]["name"]}, t0 + timedelta(days=1))
chk("급감 -> BLOCKED_SUSPECT & None", res is None and ev3[0][0] == "BLOCKED_SUSPECT")
chk("급감 시 기존 10건 보존", len(stG["quotes"]) == 10)

print("\n✅ 모든 테스트 통과")
