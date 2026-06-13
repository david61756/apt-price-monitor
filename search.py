#!/usr/bin/env python3
"""관심 단지의 정확한 단지명·전용면적을 찾는 헬퍼.

config.yaml의 match/areas를 올바르게 적기 위해, 실제 API에 등록된
단지명과 전용면적(㎡)을 지역 단위로 조회해 보여준다.

사용법:
    python search.py "경기도 용인시 수지구"            # 그 지역 모든 단지(최근 6개월)
    python search.py "경기도 용인시 수지구" 수지삼성     # 키워드 포함 단지만
    python search.py 41465 이매촌 --months 12          # 코드 직접 지정 + 기간 지정
"""
import argparse
import os
from collections import defaultdict

import monitor
from lawd import resolve_lawd_cd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region", help="시군구명(예: '경기도 용인시 수지구') 또는 법정동코드 5자리")
    ap.add_argument("keywords", nargs="*", help="단지명에 포함될 키워드(여러 개 가능)")
    ap.add_argument("--months", type=int, default=6, help="최근 몇 개월 조회 (기본 6)")
    args = ap.parse_args()

    monitor.load_env()
    key = os.environ.get("MOLIT_API_KEY")
    if not key:
        raise SystemExit("MOLIT_API_KEY가 없습니다. .env를 확인하세요.")

    lawd = args.region if args.region.isdigit() and len(args.region) == 5 \
        else resolve_lawd_cd(args.region)
    months = monitor.target_months(__import__("datetime").datetime.now(monitor.KST),
                                   args.months - 1)
    print(f"지역코드 {lawd} · 최근 {args.months}개월({months[-1]}~{months[0]}) 조회 중...\n")

    # 단지명 -> 전용면적 정수대역 -> 건수
    agg = defaultdict(lambda: defaultdict(int))
    for ymd in months:
        for r in monitor.fetch_month(key, lawd, ymd):
            nm = r["apt_nm"]
            if args.keywords and not any(k in nm for k in args.keywords):
                continue
            agg[nm][int(r["area"])] += 1

    if not agg:
        print("조회 결과 없음 — 키워드를 줄이거나 --months를 늘려보세요.")
        return

    print(f"{'단지명':28s} 전용면적㎡(거래수)")
    print("-" * 70)
    for nm in sorted(agg):
        areas = ", ".join(f"{a}㎡({c})" for a, c in sorted(agg[nm].items()))
        print(f"{nm:28s} {areas}")
    print("\n💡 config.yaml 작성 팁: match에는 위 단지명의 일부를 그대로,")
    print("   areas에는 원하는 전용면적 정수(예: 84)를 적으세요. 괄호도 그대로 포함해야 합니다.")


if __name__ == "__main__":
    main()
