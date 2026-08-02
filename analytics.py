"""밴드(3개월 예상 범위)·상대가치 계산 — 순수 로직(네트워크·렌더 의존 없음).

설계 근거는 추정이 아니라 보유 데이터 실측이다(2021-08~2026-07, 946건):

1) 3개월 변화율의 **중앙값은 불안정**하다. 수지구청 현대 84㎡ 기준 연도별로
   2023 +3.5% / 2024 +2.3% / 2025 +5.7% / 2026 +6.9% 로 3배 차이가 난다.
   → 밴드 **중심에 과거 추세를 절대 반영하지 않는다**. 중심은 항상 '최근 실거래'.
   (과거 평균 +4.7%를 중심에 넣으면 상승장 편향이 그대로 미래에 박힌다.)

2) 반면 **폭(10~90% 구간)은 상대적으로 안정**하다(연도별 11~20%p, 2배 이내).
   → 폭만 과거 분포에서 추정한다.

3) 하락기(2022)는 거래절벽으로 표본이 적다 → 밴드 하단이 낙관적으로 치우친다.
   → UI에 반드시 고지한다(이 모듈은 `caveats`로 노출).

한계(솔직히): 8억 기준 3개월 폭이 약 -3%~+15%로 넓어 점 예측 대체재가 못 된다.
'맞히는 도구'가 아니라 '변동 범위를 인지시키는 도구'로만 쓴다.
"""
from collections import defaultdict
from statistics import median

FWD_LO_DAYS, FWD_HI_DAYS = 75, 105     # '3개월 뒤'로 볼 구간
MIN_PAIRS_OWN = 8                       # 자체 분포를 쓰기 위한 최소 쌍 수
MIN_DEALS_SHOW = 5                      # 이 미만이면 밴드 자체를 만들지 않음
RECENT_DAYS = 90                        # 밴드 중심(최근 실거래 중앙값) 산정 구간
PYEONG = 3.3058                         # ㎡ → 평
# 개별 체결가 산포 하한: 동일 단지·평형·분기 내 로그가격 잔차 sd 실측 η=0.056(815건)
# → ±1.2816η ≈ ±7.2%. 시장이 정지해 있어도 층·향·동에 따라 이만큼 흩어지므로
#   밴드 반폭이 이보다 좁으면 비현실적이다(특히 상승장 표본에서 하단이 중심에 붙는 문제 보정).
MIN_HALF_WIDTH_PCT = 7.2


def _day(date_str):
    """YYYY-MM-DD → 대략적 일수(비교용). 월 31일 근사로 충분(구간 판정만 함)."""
    y, m, d = (int(x) for x in date_str.split("-"))
    return y * 372 + m * 31 + d


def _q(sorted_vals, p):
    """정렬된 리스트의 p분위수(0~1). 선형보간 없이 인덱스 방식(표본이 적어 과신 방지)."""
    if not sorted_vals:
        return None
    i = int(len(sorted_vals) * p)
    return sorted_vals[min(i, len(sorted_vals) - 1)]


def forward_changes(deals):
    """같은 단위 내에서 '약 3개월 뒤' 거래쌍의 변화율(%) 목록.

    주의: 이 값은 '과거에 실제로 일어난 3개월 변화'의 분포일 뿐 예측이 아니다.
    """
    ds = sorted(deals, key=lambda x: x["date"])
    out = []
    for i, a in enumerate(ds):
        t0 = _day(a["date"])
        if not a.get("amount"):
            continue
        for b in ds[i + 1:]:
            gap = _day(b["date"]) - t0
            if gap > FWD_HI_DAYS:
                break
            if gap >= FWD_LO_DAYS:
                out.append((b["amount"] - a["amount"]) / a["amount"] * 100)
    return out


def unit_key(d):
    return (d.get("complex", ""), int(d.get("area") or 0))


def compute_analytics(deals, now_date=None):
    """전체 거래 → 단위(단지×전용면적대)별 밴드·상대가치.

    반환: {"units": {key: {...}}, "pooled": {...}, "caveats": [...]}
    key는 대시보드에서 쓰기 쉽게 "단지명|84" 형태 문자열.
    """
    act = [d for d in deals if not d.get("cancelled") and d.get("amount")]
    groups = defaultdict(list)
    for d in act:
        groups[unit_key(d)].append(d)

    # 전체 풀링 분포 — 자체 표본이 부족한 단위의 대체재(shrinkage)
    pooled = sorted(c for g in groups.values() for c in forward_changes(g))
    pooled_band = {
        "p10": _q(pooled, 0.10), "p50": median(pooled) if pooled else None,
        "p90": _q(pooled, 0.90), "n": len(pooled),
    }

    latest_date = max((d["date"] for d in act), default=now_date or "")
    units = {}
    for (cx, area), g in groups.items():
        g.sort(key=lambda x: x["date"])
        n = len(g)
        last = g[-1]
        # ── 밴드 중심: 최근 90일 실거래 중앙값. 과거 추세는 반영하지 않는다.
        #    최근 거래가 없으면 '최근 3건의 중앙값'으로 대체 — 마지막 1건이 이상거래(증여성·특수관계)면
        #    중심이 통째로 왜곡되기 때문(실제 도담 109㎡에서 -29% 단발 거래로 발생).
        cut = _day(latest_date) - RECENT_DAYS
        recent = [d for d in g if _day(d["date"]) >= cut]
        if recent:
            center = int(median([d["amount"] for d in recent]))
        else:
            center = int(median([d["amount"] for d in g[-3:]]))

        chg = sorted(forward_changes(g))
        if len(chg) >= MIN_PAIRS_OWN:
            src, p10, p90 = "own", _q(chg, 0.10), _q(chg, 0.90)
        elif pooled_band["p10"] is not None:
            src, p10, p90 = "pooled", pooled_band["p10"], pooled_band["p90"]
        else:
            src = p10 = p90 = None

        band = None
        if src and n >= MIN_DEALS_SHOW:
            # 상승장 표본이면 p10이 양수가 되어 '하단 > 현재가'가 된다(= 무조건 오른다는 주장).
            # 단순히 현재가로 clamp만 하면 이번엔 '하단 = 현재가'(= 떨어질 수 없다)가 되어
            # 여전히 비현실적이다. 그래서 개별 체결가 산포(η) 하한을 함께 적용한다.
            lo_pct, hi_pct = min(p10, -MIN_HALF_WIDTH_PCT), max(p90, MIN_HALF_WIDTH_PCT)
            clamped = (p10 > -MIN_HALF_WIDTH_PCT) or (p90 < MIN_HALF_WIDTH_PCT)
            lo, hi = int(center * (1 + lo_pct / 100)), int(center * (1 + hi_pct / 100))
            band = {
                "center": center, "lo": lo, "hi": hi,
                "p10": round(p10, 1), "p90": round(p90, 1),
                "source": src, "pairs": len(chg),
                "recent_n": len(recent), "clamped": clamped,
            }

        units[f"{cx}|{area}"] = {
            "complex": cx, "area_band": area, "deals": n,
            "lawd_cd": last.get("lawd_cd", ""),
            "months": len(set(d["date"][:7] for d in g)),
            "last_date": last["date"], "last_amount": last["amount"],
            "center": center,
            "pyeong": round(center * PYEONG / (last.get("area") or area)) if area else 0,
            "band": band,
            "reliable": n >= 30 and (band or {}).get("source") == "own",
        }

    # ── 상대가치: **같은 지역(lawd_cd) + 같은 전용면적대**끼리만 비교한다.
    #    지역이 다르면 시장 자체가 달라 평단가 비교가 무의미하다
    #    (시흥 2,327만/평을 수지구 중앙값과 비교해 "-54% 저평가"로 읽는 오류 방지).
    by_peer = defaultdict(list)
    for k, u in units.items():
        if u["pyeong"]:
            by_peer[(u["lawd_cd"], u["area_band"])].append((k, u["pyeong"]))
    for (_lawd, _area), lst in by_peer.items():
        if len(lst) < 2:                     # 같은 지역·평형 비교군이 없으면 산출 불가
            continue
        med = median([p for _, p in lst])
        for k, p in lst:
            units[k]["rel"] = {
                "peer_median": round(med), "gap_pct": round((p - med) / med * 100, 1),
                "peers": len(lst),
            }

    caveats = [
        "밴드는 예측이 아니라 과거 3개월 변동폭의 분포입니다. 폭이 넓어 점 예측을 대체하지 못합니다.",
        "하락기(2022)는 거래절벽으로 표본이 적어 밴드 하단이 낙관적으로 치우칠 수 있습니다.",
        "표본이 적은 단위는 전체 분포로 대체(pooled)하며 신뢰도가 낮습니다.",
        "평단가 격차는 '저평가' 신호가 아닙니다. 보유 데이터로 검증한 결과 격차가 큰 단지가 "
        "이후 12개월에 오히려 더 뒤처졌습니다(방향 적중률 29.9%, gap≤-15% 단지의 초과수익 중앙값 -6.5%). "
        "생활권·연식이 다른 상품의 영구적 품질차로 보는 것이 타당합니다.",
    ]
    return {"units": units, "pooled": pooled_band, "caveats": caveats}
