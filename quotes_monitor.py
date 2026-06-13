#!/usr/bin/env python3
"""네이버페이 부동산 호가(매물) 모니터링 — 엔트리포인트.

사용법:
    python quotes_monitor.py             # 호가 수집 → 중복제거/변동감지 → 저장 → 알림 → 대시보드
    python quotes_monitor.py --dry-run   # 저장/알림 없이 감지 결과만
    python quotes_monitor.py --no-notify # 알림 없이 저장만

전제: .env에 로그인된 네이버 세션(NAVER_AUTH, NAVER_COOKIE)이 있어야 한다(README 참고).
매매(monitor.py)와 별개 파일(quotes_state.json)에 누적하며 대시보드 '호가' 탭에 표시된다.
"""
import argparse
import sys
from datetime import datetime

import monitor                       # load_env/load_config/fmt_money/send_telegram/KST/STATE_PATH 재사용
import naver_adapter
import quotes as Q
from dashboard import render_dashboard


def build_quote_messages(events):
    """reconcile 이벤트 → 텔레그램 메시지(HTML)."""
    msgs = []
    for ev in events:
        kind = ev[0]
        if kind == "NEW":
            r = ev[1]
            tail = "" if not r.get("relist_of") else " (재등록 추정)"
            msgs.append("\n".join([
                "🏷️ <b>신규 호가</b>" + tail,
                f"<b>{r['apt_nm']}</b> 전용 {r['area']:g}㎡ · {r['floor_self'] or '?'}층"
                + (f" · {r['direction']}향" if r.get('direction') else ""),
                f"💰 <b>{monitor.fmt_money(r['price'])}원</b> ({r['trade_type']})"
                + (f" · {r['realtor']}" if r.get('realtor') else ""),
                f"{r['feature']}" if r.get("feature") else "",
            ]).strip())
        elif kind in ("PRICE_DOWN", "PRICE_UP"):
            r, old = ev[1], ev[2]
            diff = r["price"] - old
            pct = diff / old * 100 if old else 0
            arrow = "🔻 인하" if kind == "PRICE_DOWN" else "🔺 인상"
            msgs.append("\n".join([
                f"{arrow} <b>호가 변동</b>",
                f"<b>{r['apt_nm']}</b> 전용 {r['area']:g}㎡ · {r['floor_self'] or '?'}층",
                f"{monitor.fmt_money(old)} → <b>{monitor.fmt_money(r['price'])}원</b>"
                f" ({'+' if diff > 0 else ''}{monitor.fmt_money(diff)}, {pct:+.1f}%)",
            ]))
        elif kind == "GONE":
            r = ev[1]
            msgs.append("\n".join([
                "⛔ <b>매물 내려감</b>",
                f"<b>{r['apt_nm']}</b> 전용 {r['area']:g}㎡ · {r['floor_self'] or '?'}층",
                f"마지막 호가 {monitor.fmt_money(r['price'])}원",
            ]))
        elif kind == "EMPTY_SUSPECT":
            msgs.append(f"⚠ <b>{ev[1]}</b> 매물 0건 — 세션 만료/차단 의심 (이번 회차 정리 스킵)")
        elif kind == "BLOCKED_SUSPECT":
            msgs.append(f"⚠ <b>차단 의심</b> — 전체 매물 급감(직전 {ev[1]} → {ev[2]}건). "
                        f"저장을 건너뛰었습니다. 네이버 재로그인 후 세션을 갱신하세요.")
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="저장/알림 없이 감지만")
    ap.add_argument("--no-notify", action="store_true", help="알림 없이 저장만")
    ap.add_argument("--curl", action="store_true",
                    help="cURL/.env 세션 방식 사용(기본: Playwright 자동 로그인)")
    ap.add_argument("--headful", action="store_true", help="Playwright 브라우저 창을 띄워 실행")
    args = ap.parse_args()

    monitor.load_env()
    cfg = monitor.load_config()
    targets = [c for c in cfg["complexes"] if c.get("naver_id")]
    if not targets:
        sys.exit("config.yaml의 어떤 단지에도 naver_id가 없습니다. "
                 "python naver_lookup.py \"단지명\" 으로 번호를 찾아 추가하세요.")

    now = datetime.now(monitor.KST)
    first_run = not Q.QUOTES_PATH.exists()
    qstate = Q.load_quotes_state()

    if args.curl:
        session, err = naver_adapter.build_session()
        if err:
            sys.exit("❌ " + err)
        fetched, scanned = naver_adapter.fetch_all(cfg, session)
    else:
        try:
            import naver_playwright
        except ImportError:
            sys.exit("Playwright가 없습니다. 'pip install playwright && python -m playwright "
                     "install chromium' 후 다시 시도하거나, --curl 방식을 쓰세요.")
        fetched, scanned = naver_playwright.fetch_all_playwright(cfg, headless=not args.headful)
    quotes, events = Q.reconcile(qstate, fetched, scanned, now)

    # 차단 의심 → 저장 스킵, 경고만
    if quotes is None:
        print("⚠ 차단 의심으로 저장을 건너뜁니다.")
        if cfg["naver"].get("notify") and not (args.dry_run or args.no_notify):
            monitor.send_telegram(build_quote_messages(events))
        return

    # 관심단지에서 빠진 매물 정리
    before = len(quotes)
    qstate["quotes"] = Q.prune_quotes(quotes, cfg["complexes"])
    if before - len(qstate["quotes"]):
        print(f"정리: 관심단지에 없는 매물 {before - len(qstate['quotes'])}건 제거")

    # 요약 출력
    kinds = [e[0] for e in events]
    print(f"\n호가 수집: 활성 {sum(1 for q in qstate['quotes'].values() if q['status']=='active')}건 · "
          f"신규 {kinds.count('NEW')} · 인하 {kinds.count('PRICE_DOWN')} · "
          f"인상 {kinds.count('PRICE_UP')} · 내려감 {kinds.count('GONE')}")

    messages = build_quote_messages(
        [e for e in events if e[0] not in ("EMPTY_SUSPECT",)]) if not first_run else []
    # 세션만료 의심 경고는 항상 포함
    messages += [m for e in events if e[0] == "EMPTY_SUSPECT"
                 for m in build_quote_messages([e])]

    if first_run:
        print("ℹ 호가 최초 실행: 기준선으로 저장만 하고 알림은 보내지 않습니다.")
    elif messages and not (args.dry_run or args.no_notify) and cfg["naver"].get("notify"):
        monitor.send_telegram(messages)
    elif messages:
        print("\n[호가 알림 미리보기]")
        for m in messages:
            print("-" * 40)
            print(m.replace("<b>", "").replace("</b>", ""))

    if args.dry_run:
        print("\n--dry-run: quotes_state.json/대시보드를 갱신하지 않았습니다.")
        return

    Q.save_quotes_state(qstate)
    # 대시보드: 매매(state.json) + 호가(qstate) 함께 렌더
    state = {}
    if monitor.STATE_PATH.exists():
        import json
        state = json.loads(monitor.STATE_PATH.read_text(encoding="utf-8"))
    monitor.DASHBOARD_PATH.parent.mkdir(exist_ok=True)
    render_dashboard(state, cfg, monitor.DASHBOARD_PATH, quotes_state=qstate)
    print(f"quotes_state.json 저장 (활성+소멸 {len(qstate['quotes'])}건), 대시보드 갱신.")


if __name__ == "__main__":
    main()
