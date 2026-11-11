#!/usr/bin/env python3
"""정기 업데이트 오케스트레이터.

실거래(monitor.py)와 호가(quotes_monitor.py)를 차례로 실행하고,
실행 전후 데이터를 비교해 '변동사항'을 한 건으로 요약해 Discord로 알린다.

- launchd(매일 08:00/14:00/18:00 KST) 또는 수동(`python update.py`) 실행.
- Discord 웹훅은 .env의 DISCORD_WEBHOOK_URL 사용(없으면 콘솔 출력으로 대체).

사용법:
    python update.py            # 실거래+호가 갱신 → 변동 요약 Discord 전송
    python update.py --no-notify # Discord 전송 없이 요약만 콘솔 출력
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime

import requests

import monitor
from monitor import KST, STATE_PATH, fmt_money, load_env
from quotes import QUOTES_PATH, retag_quotes

# 요약에 단지별로 나열할 최대 항목 수(초과분은 '외 N건'으로 축약)
MAX_ITEMS_PER_SECTION = 8
DISCORD_LIMIT = 1900  # 2000자 한도 여유


# ----------------------------------------------------------------- 스냅샷/diff

def _load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def snapshot():
    """현재 state.json·quotes_state.json을 비교용 형태로 읽는다."""
    deals = {did: d for did, d in _load_json(STATE_PATH).get("deals", {}).items()}
    quotes = {ano: q for ano, q in _load_json(QUOTES_PATH).get("quotes", {}).items()}
    return deals, quotes


def diff_deals(before, after):
    """신규 거래·해제 거래를 가려낸다(설정 변경으로 사라진 건은 무시)."""
    new, cancelled = [], []
    for did, d in after.items():
        if did not in before:
            if not d.get("cancelled"):
                new.append(d)
        else:
            if d.get("cancelled") and not before[did].get("cancelled"):
                cancelled.append(d)
    new.sort(key=lambda d: d.get("date", ""))
    cancelled.sort(key=lambda d: d.get("date", ""))
    return new, cancelled


def diff_quotes(before, after):
    """호가 신규·인하·인상·내려감을 가려낸다(설정 변경으로 제거된 건은 무시)."""
    new, down, up, gone = [], [], [], []
    for ano, q in after.items():
        prev = before.get(ano)
        if prev is None:
            if q.get("status") == "active":
                new.append(q)
        else:
            # 둘 다 활성인데 가격이 바뀐 경우
            if q.get("status") == "active" and prev.get("status") == "active":
                pp, cp = prev.get("price"), q.get("price")
                if pp is not None and cp is not None and cp != pp:
                    (down if cp < pp else up).append((q, pp, cp))
            # 활성 → 내려감(gone)
            if q.get("status") == "gone" and prev.get("status") == "active":
                gone.append(q)
    return new, down, up, gone


# ----------------------------------------------------------------- 메시지 구성

def _unit_id(q):
    """같은 세대 식별자. 동·층·향이 확인되면 unit_key(여러 중개사 중복 등록을 하나로), 아니면 매물번호."""
    if q.get("unit_key_confident") and q.get("unit_key"):
        return q["unit_key"]
    return "article:" + str(q.get("article_no"))


def _active_units(quotes):
    """활성 매물을 세대 단위로 묶는다 → {unit_id: [매물, ...]}"""
    units = {}
    for q in quotes.values():
        if q.get("status") == "active":
            units.setdefault(_unit_id(q), []).append(q)
    return units


def diff_units(before, after):
    """호가 변동을 '세대' 단위로 가린다 — 중개사 광고 갱신(재등록)·중복 등록은 변동이 아니다.

    - 신규: 처음 보는 세대가 나옴 (재등록·같은 매물 재등장은 제외)
    - 인하/인상: 실제 가격 수정(같은 매물의 가격 변경, 재등록하며 바꾼 가격)이 있고
      그 결과 세대 최저 호가가 달라졌을 때만. 중개사 한 곳이 광고를 내렸거나, 다른 중개사가
      여전히 더 싸게 내놓고 있는 상태에서 한 곳만 값을 올린 것은 알리지 않는다.
    - 소멸: 그 세대 매물이 모두 내려감 (관심단지에서 빠져 정리된 건 제외)
    반환 (new, down, up, gone) — new/gone: [(대표매물, 매물수)], down/up: [(대표매물, 이전가, 현재가, 매물수)]
    """
    bu, au = _active_units(before), _active_units(after)
    new, down, up, gone = [], [], [], []
    for uid, qs in au.items():
        fresh, srcs, moved = uid not in bu, [], False
        for q in qs:
            src = before.get(q["article_no"])     # 이미 알던 매물(재등장 포함)
            if src is None and q.get("relist_of"):
                src = after.get(q["relist_of"]) or before.get(q["relist_of"])   # 재등록 원본
            if src is None:
                continue
            fresh = False
            srcs.append(src)
            moved = moved or src["price"] != q["price"]
        rep = min(qs, key=lambda q: q["price"])
        if fresh:
            new.append((rep, len(qs)))
            continue
        if not moved:
            continue
        old = min(q["price"] for q in bu[uid]) if uid in bu else min(x["price"] for x in srcs)
        if rep["price"] < old:
            down.append((rep, old, rep["price"], len(qs)))
        elif rep["price"] > old:
            up.append((rep, old, rep["price"], len(qs)))
    for uid, qs in bu.items():
        if uid not in au and any(q["article_no"] in after for q in qs):
            gone.append((min(qs, key=lambda q: q["price"]), len(qs)))
    return new, down, up, gone


def _q_label(q, cx, n=1):
    """'성복역 현대홈타운 32평(84㎡) 202동 12층 남동향 [전세] · 중개 3곳'"""
    dong, facing = q.get("building_name"), q.get("direction")
    where = ((f"{dong}동 " if dong and dong != "?" else "") + f"{q.get('floor_self') or '?'}층"
             + (f" {facing}향" if facing else ""))     # 같은 층 다른 집(향)이 같은 집처럼 보이지 않게
    tt = "" if q.get("trade_code", "A1") == "A1" else f" [{q.get('trade_type', '전세')}]"
    many = f" · 중개 {n}곳" if n > 1 else ""
    area = monitor.area_label(cx.get(q.get("complex")), q.get("area"))
    return f"{q.get('complex', q.get('apt_nm', '?'))} {area} {where}{tt}{many}"


def _d_label(d, cx):
    area = monitor.area_label(cx.get(d.get("complex")), d.get("area"))
    return f"{d.get('complex', d.get('apt_nm', '?'))} {area} {d.get('floor') or '?'}층"


def _vs_prev(d, deals):
    """직전 같은 평형(면적대) 거래 대비 등락 — monitor.find_prev_deal과 같은 기준."""
    prev = monitor.find_prev_deal(deals, d)
    if not prev:
        return ""
    diff = d["amount"] - prev["amount"]
    pct = diff / prev["amount"] * 100
    arrow = "⏸ 보합" if diff == 0 else (f"🔺+{pct:.1f}%" if diff > 0 else f"🔻{pct:.1f}%")
    return f" · 직전 {fmt_money(prev['amount'])}({prev['date'][5:]}) 대비 {arrow}"


def _bullets(items, render):
    lines = [f"• {render(it)}" for it in items[:MAX_ITEMS_PER_SECTION]]
    if len(items) > MAX_ITEMS_PER_SECTION:
        lines.append(f"• …외 {len(items) - MAX_ITEMS_PER_SECTION}건")
    return lines


def _load_alert_rules():
    """config에서 (단지명→설정, 목표가{(단지,면적):만원}, 관심 매물번호 set)를 읽는다. 실패 시 빈 값."""
    try:
        cfg = monitor.load_config()
    except SystemExit:
        return {}, {}, set()
    cx, targets, watch = {}, {}, set()
    for c in cfg.get("complexes", []):
        cx[c["name"]] = c
        for area, price in (c.get("targets") or {}).items():
            targets[(c["name"], int(area))] = int(price)
        watch.update(c.get("watch") or [])
    return cx, targets, watch


def build_summary(now, deal_diff, quote_diff, unit_diff, failures, deals=()):
    new_d, cancel_d = deal_diff
    new_q, down_q, up_q, gone_q = quote_diff      # 매물 단위 — 📌 관심 매물(매물번호 지정) 추적용
    new_u, down_u, up_u, gone_u = unit_diff       # 세대 단위 — 일반 호가 알림
    out = [f"📊 **부동산 업데이트 — {now.strftime('%Y-%m-%d %H:%M')} KST**"]

    if failures:
        out.append("⚠ " + " / ".join(failures))

    cx, targets, watch = _load_alert_rules()

    def _target_of(q):
        return targets.get((q.get("complex"), int(float(q.get("area") or 0))))

    def _hits_target(q):
        t = _target_of(q)
        return (t is not None and q.get("trade_code", "A1") == "A1"
                and q.get("price") is not None and q["price"] <= t)

    # 🎯 목표가 도달 — 새로 나왔거나 인하로 목표 이하가 된 매매 세대 (최우선 섹션)
    hit = [(q, n) for q, n in new_u if _hits_target(q)] + \
          [(q, n) for q, _old, _cur, n in down_u if _hits_target(q)]
    if hit:
        out.append("\n🎯 **목표가 도달**")
        out += _bullets(hit, lambda t: f"{_q_label(t[0], cx, t[1])} — {fmt_money(t[0]['price'])}원 "
                        f"(목표 {fmt_money(_target_of(t[0]))})")

    # 📌 관심 매물(워치) 변동 — 지정한 매물번호 그대로 추적, 축약 없이 전부 표기
    if watch:
        wlines = []
        for q in new_q:
            if q.get("article_no") in watch:
                wlines.append(f"• 📌 {_q_label(q, cx)} — 신규 {fmt_money(q['price'])}원")
        for q, pp, cp in down_q + up_q:
            if q.get("article_no") in watch:
                arrow = "🔻" if cp < pp else "🔺"
                wlines.append(f"• 📌 {arrow} {_q_label(q, cx)} — {fmt_money(pp)}→{fmt_money(cp)}원")
        for q in gone_q:
            if q.get("article_no") in watch:
                wlines.append(f"• 📌 ⬇️ {_q_label(q, cx)} — {fmt_money(q['price'])}원 내려감")
        if wlines:
            out.append("\n📌 **관심 매물**")
            out += wlines

    changed = any([new_d, cancel_d, new_u, down_u, up_u, gone_u])
    if not changed:
        out.append("\n변동 없음 — 신규/해제/호가 변동이 없습니다.")
        return "\n".join(out)

    # 실거래 — 평형 표기 + 직전 같은 평형 거래 대비 등락
    if new_d or cancel_d:
        out.append(f"\n🏠 **실거래** (신규 {len(new_d)} · 해제 {len(cancel_d)})")
        out += _bullets(new_d, lambda d: f"🆕 {_d_label(d, cx)} — {fmt_money(d['amount'])}원 "
                        f"({d['date']}){_vs_prev(d, deals)}")
        out += _bullets(cancel_d, lambda d: f"❌ {_d_label(d, cx)} — {fmt_money(d['amount'])}원 해제")

    # 호가 — 세대 기준 (재등록·중복 등록 제외)
    if new_u or down_u or up_u or gone_u:
        out.append(f"\n🏷️ **호가** — 세대 기준 (신규 {len(new_u)} · 인하 {len(down_u)} · "
                   f"인상 {len(up_u)} · 소멸 {len(gone_u)})")
        out += _bullets(new_u, lambda t: f"🆕 {_q_label(t[0], cx, t[1])} — {fmt_money(t[0]['price'])}원")
        out += _bullets(down_u, lambda t: f"🔻 {_q_label(t[0], cx, t[3])} — {fmt_money(t[1])}→{fmt_money(t[2])}원")
        out += _bullets(up_u, lambda t: f"🔺 {_q_label(t[0], cx, t[3])} — {fmt_money(t[1])}→{fmt_money(t[2])}원")
        out += _bullets(gone_u, lambda t: f"⬇️ {_q_label(t[0], cx, t[1])} — {fmt_money(t[0]['price'])}원 내려감")

    return "\n".join(out)


# ----------------------------------------------------------------- Discord 전송

def send_discord(content):
    import os
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("⚠ DISCORD_WEBHOOK_URL 미설정 — 콘솔 출력으로 대체합니다.")
        print(content)
        return
    # 2000자 한도 → 줄 단위로 나눠 전송
    chunks, cur = [], ""
    for line in content.split("\n"):
        if cur and len(cur) + len(line) + 1 > DISCORD_LIMIT:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    for chunk in chunks:
        try:
            r = requests.post(url, json={"content": chunk}, timeout=30)
            if not r.ok:
                print(f"⚠ Discord 전송 실패: {r.status_code} {r.text[:200]}")
        except requests.RequestException as e:
            print(f"⚠ Discord 전송 오류: {e}")


# --------------------------------------------------------------------- main

def _run(script):
    """하위 스크립트 실행. 실패해도 전체 업데이트는 계속 진행."""
    print(f"\n===== {script} 실행 =====", flush=True)
    res = subprocess.run([sys.executable, str(monitor.BASE_DIR / script)],
                         cwd=str(monitor.BASE_DIR))
    if res.returncode != 0:
        print(f"⚠ {script} 비정상 종료 (코드 {res.returncode})")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-notify", action="store_true", help="Discord 전송 없이 요약만 출력")
    args = ap.parse_args()

    load_env()
    before_deals, before_quotes = snapshot()

    failures = []
    if not _run("monitor.py"):
        failures.append("실거래 갱신 실패")
    if not _run("quotes_monitor.py"):
        failures.append("호가 갱신 실패")

    after_deals, after_quotes = snapshot()
    # 이번 회차에 단지명이 바뀌었어도 직전 스냅샷을 같은 기준(새 이름·unit_key)으로 맞춰 비교
    try:
        retag_quotes(before_quotes, monitor.load_config()["complexes"])
    except SystemExit:
        pass
    deal_diff = diff_deals(before_deals, after_deals)
    quote_diff = diff_quotes(before_quotes, after_quotes)
    unit_diff = diff_units(before_quotes, after_quotes)

    summary = build_summary(datetime.now(KST), deal_diff, quote_diff, unit_diff, failures,
                            list(after_deals.values()))
    print("\n" + "=" * 50 + "\n" + summary + "\n" + "=" * 50)

    if args.no_notify:
        print("\n--no-notify: Discord 전송 생략")
    else:
        send_discord(summary)


if __name__ == "__main__":
    main()
