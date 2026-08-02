"""analytics.py 순수 로직 검증 (네트워크 없이). 실행: python3 test_analytics.py"""
import analytics as A


def chk(name, cond):
    print(("✓" if cond else "✗ 실패:"), name)
    assert cond, name


def deal(date, amount, area=84.9, cx="A단지", cancelled=False, lawd="41465"):
    return {"date": date, "amount": amount, "area": area, "complex": cx,
            "cancelled": cancelled, "apt_nm": cx, "lawd_cd": lawd}


# 1) forward_changes: 75~105일 구간만 잡는다
d = [deal("2025-01-01", 100000), deal("2025-03-20", 110000),   # 78일 → 포함(+10%)
     deal("2025-06-01", 200000)]                                # 151일 → 제외
c = A.forward_changes(d)
chk("3개월 구간만 페어링", len(c) == 1 and abs(c[0] - 10.0) < 0.01)

# 2) 구간 밖(너무 이른 재거래)은 제외
d2 = [deal("2025-01-01", 100000), deal("2025-02-01", 110000)]   # 31일
chk("31일 뒤 거래는 제외", A.forward_changes(d2) == [])

# 3) 밴드 중심은 '최근 실거래'이지 과거 추세가 아니다 (핵심 설계 원칙)
#    과거에 크게 오른 이력이 있어도 중심은 최근가에 고정돼야 한다.
hist = []
base = 50000
for i in range(1, 25):            # 2년간 매월 상승 (강한 상승 추세)
    hist.append(deal(f"2025-{i:02d}-05".replace("-13-", "-12-") if i <= 12
                     else f"2026-{i-12:02d}-05", base + i * 2000))
res = A.compute_analytics(hist)
u = list(res["units"].values())[0]
last_amt = max(h["amount"] for h in hist)
chk("밴드 중심 = 최근 실거래(추세 반영 안 함)", u["band"]["center"] >= last_amt * 0.95)
chk("중심이 최근가를 상회 추정하지 않음", u["band"]["center"] <= last_amt * 1.05)

# 4) 소표본은 pooled로 대체되고 reliable=False
small = [deal("2026-01-05", 80000, cx="B단지"), deal("2026-04-05", 82000, cx="B단지"),
         deal("2026-05-05", 81000, cx="B단지"), deal("2026-06-05", 83000, cx="B단지"),
         deal("2026-07-05", 84000, cx="B단지")]
res2 = A.compute_analytics(hist + small)
b = res2["units"]["B단지|84"]
chk("소표본 → pooled 대체", b["band"] and b["band"]["source"] == "pooled")
chk("소표본 → reliable False", b["reliable"] is False)

# 5) 거래 5건 미만이면 밴드 없음
tiny = [deal("2026-06-05", 90000, cx="C단지"), deal("2026-07-05", 91000, cx="C단지")]
res3 = A.compute_analytics(hist + tiny)
chk("5건 미만 → 밴드 미생성", res3["units"]["C단지|84"]["band"] is None)

# 6) 해제 거래는 제외
canc = [deal("2026-07-10", 999999, cx="C단지", cancelled=True)]
res4 = A.compute_analytics(tiny + canc)
chk("해제거래 제외", res4["units"]["C단지|84"]["deals"] == 2)

# 7) 상대가치: 같은 면적대끼리만 비교, 중앙값 대비 괴리
peers = []
for i, (cx, amt) in enumerate([("P1", 60000), ("P2", 80000), ("P3", 100000)]):
    for m in range(1, 7):
        peers.append(deal(f"2026-0{m}-05", amt, area=84.9, cx=cx))
res5 = A.compute_analytics(peers)
p1 = res5["units"]["P1|84"]["rel"]; p3 = res5["units"]["P3|84"]["rel"]
chk("상대가치 비교군 3개", p1["peers"] == 3)
chk("싼 단지는 음수 괴리", p1["gap_pct"] < 0)
chk("비싼 단지는 양수 괴리", p3["gap_pct"] > 0)

# 8) 다른 면적대는 서로 비교하지 않는다
mixed = peers + [deal(f"2026-0{m}-05", 50000, area=59.9, cx="S1") for m in range(1, 7)]
res6 = A.compute_analytics(mixed)
chk("면적대 1개뿐이면 상대가치 없음", "rel" not in res6["units"]["S1|59"])

# ── 실데이터에서 발견된 결함 3종 회귀 테스트 ──────────────────────────

# 9) 마지막 1건이 이상거래여도 중심이 통째로 왜곡되지 않는다 (도담 109㎡ -29% 단발 사례)
#    최근 90일에 거래가 없으면 최근 3건 중앙값을 쓴다.
old = [deal("2025-06-19", 64000, cx="D단지"), deal("2025-10-18", 65000, cx="D단지"),
       deal("2026-01-09", 66000, cx="D단지"), deal("2026-04-20", 47000, cx="D단지")]
far = [deal("2026-07-30", 90000, cx="Z단지")]      # 최신일을 밀어 D단지를 '최근 90일 밖'으로
res9 = A.compute_analytics(old + far + [deal(f"2026-0{m}-01", 90000, cx="Z단지") for m in range(1, 7)])
dc = res9["units"]["D단지|84"]["center"]
chk("이상거래 단발이 중심을 장악하지 않음", dc == 65000)

# 10) 상승장 표본이어도 밴드는 현재가를 포함한다 (하단 > 현재가 금지)
bull = []
p = 80000
for i in range(1, 13):                             # 매월 +3% 상승만 있는 표본
    bull.append(deal(f"2026-{i:02d}-05".replace("-13-", "-12-") if i <= 12 else "2026-12-05",
                     int(p), cx="U단지"))
    p *= 1.03
res10 = A.compute_analytics(bull)
ub = res10["units"]["U단지|84"]["band"]
chk("밴드 하단 ≤ 현재가 (상승장 편향 보정)", ub["lo"] <= ub["center"] <= ub["hi"])
chk("보정 발생 시 clamped 플래그", ub["clamped"] is True)

# 11) 지역이 다르면 상대가치를 비교하지 않는다 (시흥 vs 수지 오비교 방지)
mix = []
for m in range(1, 7):
    mix.append(deal(f"2026-0{m}-05", 100000, area=59.9, cx="수지단지", lawd="41465"))
    mix.append(deal(f"2026-0{m}-05", 42000, area=59.9, cx="시흥단지", lawd="41390"))
res11 = A.compute_analytics(mix)
chk("타지역과 비교 안 함(수지 단독 → rel 없음)", "rel" not in res11["units"]["수지단지|59"])
chk("타지역과 비교 안 함(시흥 단독 → rel 없음)", "rel" not in res11["units"]["시흥단지|59"])

print("\n✅ 모든 테스트 통과")
