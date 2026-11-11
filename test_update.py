"""update.py 알림 로직 검증 (네트워크·Discord 없이). 실행: python test_update.py"""
import copy

import monitor
from update import _d_label, _q_label, _vs_prev, diff_units


def chk(name, cond):
    print(("✓" if cond else "✗ 실패:"), name)
    assert cond, name


CX = {"현대홈타운": {"name": "현대홈타운", "pyeong": {59: 24, 84: 32}}}


def quote(an, price, unit="U1", status="active", confident=True, relist_of=None, area=84.0):
    return {"article_no": an, "complex": "현대홈타운", "price": price, "status": status,
            "unit_key": unit, "unit_key_confident": confident, "relist_of": relist_of,
            "trade_code": "A1", "building_name": "202", "floor_self": "12", "direction": "남동",
            "area": area}


def state(*qs):
    return {q["article_no"]: q for q in qs}


# 1) 평형 표기
chk("매핑 있으면 '32평(84㎡)'", monitor.area_label(CX["현대홈타운"], 84.85) == "32평(84㎡)")
chk("매핑 없으면 '84㎡'", monitor.area_label({}, 84.85) == "84㎡")
chk("호가 라벨에 평형·동·층·향·중개수",
    _q_label(quote("A", 117000), CX, 3) == "현대홈타운 32평(84㎡) 202동 12층 남동향 · 중개 3곳")
chk("실거래 라벨에 평형(소수 면적 숨김)",
    _d_label({"complex": "현대홈타운", "area": 59.9328, "floor": "18"}, CX) == "현대홈타운 24평(59㎡) 18층")

# 2) 같은 세대를 여러 중개사가 올림 → 신규 1세대
new, down, up, gone = diff_units({}, state(quote("A", 117000), quote("B", 118000)))
chk("중복 등록 2건 → 신규 1세대(대표=최저가, 중개 2곳)",
    len(new) == 1 and new[0][0]["article_no"] == "A" and new[0][1] == 2)

# 3) 중개사가 광고 갱신(내렸다가 같은 가격으로 재등록) → 알림 없음
before = state(quote("X", 120000))
after = state(quote("X", 120000, status="gone"), quote("Y", 120000, relist_of="X"))
chk("같은 가격 재등록 → 신규·소멸 없음", diff_units(before, after) == ([], [], [], []))

# 4) 재등록하면서 가격을 내림 → 인하로 잡음
after = state(quote("X", 120000, status="gone"), quote("Y", 115000, relist_of="X"))
_, down, _, _ = diff_units(before, after)
chk("재등록 + 가격 인하 → 인하 1건(12억→11.5억)", len(down) == 1 and down[0][1:3] == (120000, 115000))

# 5) 두 중개사 중 한 곳만 내림 → 세대는 아직 시장에 있음
before = state(quote("A", 117000), quote("B", 118000))
after = state(quote("A", 117000, status="gone"), quote("B", 118000))
chk("한 곳만 내림 → 소멸·인상 모두 아님(광고 하나 사라진 것)", diff_units(before, after) == ([], [], [], []))

# 5b) 같은 매물이 가격을 고침 → 인하
after = state(quote("A", 115000), quote("B", 118000))
_, down, _, _ = diff_units(before, after)
chk("같은 매물 가격 수정 → 인하 1건(중개 2곳)", len(down) == 1 and down[0][1:] == (117000, 115000, 2))

# 5b-2) 다른 중개사가 여전히 더 싸게 내놓은 상태에서 한 곳만 값을 올림 → 세대 최저가 그대로라 무시
after = state(quote("A", 117000), quote("B", 125000))
chk("한 곳 인상이어도 세대 최저가 그대로면 알림 없음", diff_units(before, after) == ([], [], [], []))

# 5c) 내려갔던 같은 매물번호가 다시 나타남 → 신규 아님
after = state(quote("X", 120000))
chk("같은 매물 재등장 → 신규 아님", diff_units(state(quote("X", 120000, status="gone")), after) == ([], [], [], []))

# 6) 세대 매물이 모두 내려감 → 소멸
after = state(quote("A", 117000, status="gone"), quote("B", 118000, status="gone"))
chk("모두 내려감 → 소멸 1세대", len(diff_units(before, after)[3]) == 1)

# 7) 관심단지에서 빠져 정리된 매물은 소멸로 보지 않음
chk("config 정리(after에 없음) → 소멸 아님", diff_units(before, {})[3] == [])

# 8) 동·층·향을 모르는 매물은 매물 단위로 따로 셈
qs = state(quote("P", 100000, confident=False), quote("Q", 101000, confident=False))
chk("unit 불확실 → 매물별 신규 2건", len(diff_units({}, qs)[0]) == 2)

# 9) 원본을 바꾸지 않음
snap = state(quote("A", 117000))
frozen = copy.deepcopy(snap)
diff_units(snap, snap)
chk("diff_units는 입력을 변경하지 않음", snap == frozen)

# 10) 실거래 직전 같은 평형 대비
deals = [
    {"apt_seq": "S", "area": 84.85, "amount": 107000, "date": "2026-10-17", "cancelled": False},
    {"apt_seq": "S", "area": 59.93, "amount": 104000, "date": "2026-10-31", "cancelled": False},
]
d = {"apt_seq": "S", "area": 84.85, "amount": 116500, "date": "2026-11-05", "cancelled": False}
s = _vs_prev(d, deals + [d])
chk("직전 비교는 같은 평형(84)만 — 더 최근 59㎡ 거래는 무시", "10억 7,000만(10-17)" in s and "+8.9%" in s)
chk("직전 거래 없으면 빈 문자열", _vs_prev(dict(d, apt_seq="NONE"), deals) == "")

print("\n✅ 모든 테스트 통과")
