#!/usr/bin/env python3
"""밴드 커버리지 워크포워드 백테스트.

질문은 하나다: **대시보드에 보여주는 밴드가 실제로 몇 % 맞는가?**

방법(룩어헤드를 막는 것이 전부):
  - 매월 말을 as-of 시점 T로 잡는다.
  - T 시점에 '알 수 있었던' 거래만으로 밴드를 만든다(계약일 ≤ T-임베고, 해제도 그때 알려진 것만).
    신고지연은 보유 데이터 실측 p90 ≈ 41일 → 기본 임베고 45일.
  - 그 뒤 H일(기본 91일) 안에 실제로 체결된 **개별 거래가**가 밴드 안에 들어왔는지 센다.
    (중앙값이 아니라 개별 체결가로 평가해야 카드에 표시되는 의미와 일치한다.)

정직성 노트: 임베고를 빼면 커버리지가 올라가지만 그건 그 시점에 몰랐던 정보를 쓴 결과다.
따라서 기본값은 임베고를 켠 상태이며, 비교를 위해 끈 경우도 함께 출력한다.

실행: python3 backtest_bands.py [--embargo 45] [--horizon 91]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from analytics import _shift, compute_analytics

STATE = Path(__file__).resolve().parent / "state.json"


def month_ends(start, end):
    """start~end 사이 각 달의 말일(YYYY-MM-DD) 목록."""
    from datetime import date, timedelta
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while True:
        nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
        last = (nxt - timedelta(days=1)).isoformat()
        if last > end:
            break
        if last >= start:
            out.append(last)
        y, m = nxt.year, nxt.month
    return out


def run(deals, embargo, horizon, verbose=True):
    dates = sorted(d["date"] for d in deals)
    asofs = month_ends(_shift(dates[0], 365), _shift(dates[-1], -horizon))
    rows = []          # (asof, 적중여부) — 개별 체결가 단위
    per_asof = defaultdict(lambda: [0, 0])
    widths, below, above = [], 0, 0
    center_bias = []

    for T in asofs:
        an = compute_analytics(deals, asof=T, embargo_days=embargo)
        for key, u in an["units"].items():
            b = u.get("band")
            if not b:
                continue
            cx, area = u["complex"], u["area_band"]
            # 평가 대상: T 다음날 ~ T+horizon 사이에 '실제 계약'된 거래(해제 제외)
            fut = [d for d in deals
                   if d.get("complex") == cx and int(d.get("area") or 0) == area
                   and not d.get("cancelled")
                   and T < d["date"] <= _shift(T, horizon)]
            if not fut:
                continue
            w = (b["hi"] - b["lo"]) / b["center"] * 100
            for d in fut:
                hit = b["lo"] <= d["amount"] <= b["hi"]
                rows.append(hit)
                per_asof[T][0] += hit
                per_asof[T][1] += 1
                if d["amount"] < b["lo"]:
                    below += 1
                elif d["amount"] > b["hi"]:
                    above += 1
                widths.append(w)
                center_bias.append((b["center"] - d["amount"]) / d["amount"] * 100)

    n = len(rows)
    if not n:
        return None
    cov = sum(rows) / n * 100
    by = [c / t * 100 for c, t in per_asof.values() if t >= 3]
    res = {
        "embargo": embargo, "horizon": horizon, "n": n, "asofs": len(per_asof),
        "coverage": cov, "below": below / n * 100, "above": above / n * 100,
        "width": median(widths), "center_bias": median(center_bias),
        "asof_med": median(by) if by else None,
        "asof_min": min(by) if by else None, "asof_max": max(by) if by else None,
    }
    if verbose:
        print(f"\n── 임베고 {embargo}일 / 지평 {horizon}일 ──")
        print(f"  평가 체결건 {n}건 · as-of 시점 {len(per_asof)}개")
        print(f"  커버리지        {cov:.1f}%   (하단이탈 {res['below']:.1f}% / 상단이탈 {res['above']:.1f}%)")
        print(f"  밴드 폭(중앙)   {res['width']:.1f}%")
        print(f"  중심 편향       {res['center_bias']:+.2f}%  (양수면 밴드 중심이 실제보다 높음)")
        if by:
            print(f"  시점별 커버리지 중앙 {res['asof_med']:.0f}% · 범위 {res['asof_min']:.0f}~{res['asof_max']:.0f}%")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embargo", type=int, default=45)
    ap.add_argument("--horizon", type=int, default=91)
    ap.add_argument("--save", action="store_true",
                    help="결과를 band_backtest.json에 저장(대시보드가 실측 적중률 표기에 사용)")
    args = ap.parse_args()
    deals = list(json.loads(STATE.read_text(encoding="utf-8"))["deals"].values())
    print(f"=== 밴드 워크포워드 백테스트 (보유 {len(deals)}건) ===")
    base = run(deals, args.embargo, args.horizon)
    print("\n[비교] 임베고를 끄면(= 그때 몰랐을 정보 사용):")
    naive = run(deals, 0, args.horizon)
    print("\n[민감도] 임베고 30/60일:")
    run(deals, 30, args.horizon)
    run(deals, 60, args.horizon)
    if base:
        print(f"\n※ 대시보드 표기 근거: 임베고 {args.embargo}일 기준 실측 커버리지 "
              f"{base['coverage']:.0f}% (시점별 {base['asof_min']:.0f}~{base['asof_max']:.0f}%)")
        if args.save:
            out = Path(__file__).resolve().parent / "band_backtest.json"
            base["naive_coverage"] = naive["coverage"] if naive else None
            base["deals_used"] = len(deals)
            out.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"저장: {out.name}")


if __name__ == "__main__":
    main()
