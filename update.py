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
from quotes import QUOTES_PATH

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

def _q_label(q):
    floor = q.get("floor_self") or "?"
    return f"{q.get('complex', q.get('apt_nm', '?'))} · {q.get('area', '?')}㎡ {floor}층"


def _d_label(d):
    return (f"{d.get('complex', d.get('apt_nm', '?'))} 전용{d.get('area', '?')}㎡ "
            f"{d.get('floor') or '?'}층")


def _bullets(items, render):
    lines = [f"• {render(it)}" for it in items[:MAX_ITEMS_PER_SECTION]]
    if len(items) > MAX_ITEMS_PER_SECTION:
        lines.append(f"• …외 {len(items) - MAX_ITEMS_PER_SECTION}건")
    return lines


def build_summary(now, deal_diff, quote_diff, failures):
    new_d, cancel_d = deal_diff
    new_q, down_q, up_q, gone_q = quote_diff
    out = [f"📊 **부동산 업데이트 — {now.strftime('%Y-%m-%d %H:%M')} KST**"]

    if failures:
        out.append("⚠ " + " / ".join(failures))

    changed = any([new_d, cancel_d, new_q, down_q, up_q, gone_q])
    if not changed:
        out.append("\n변동 없음 — 신규/해제/호가 변동이 없습니다.")
        return "\n".join(out)

    # 실거래
    if new_d or cancel_d:
        out.append(f"\n🏠 **실거래** (신규 {len(new_d)} · 해제 {len(cancel_d)})")
        out += _bullets(new_d, lambda d: f"🆕 {_d_label(d)} — {fmt_money(d['amount'])}원 ({d['date']})")
        out += _bullets(cancel_d, lambda d: f"❌ {_d_label(d)} — {fmt_money(d['amount'])}원 해제")

    # 호가
    if new_q or down_q or up_q or gone_q:
        out.append(f"\n🏷️ **호가** (신규 {len(new_q)} · 인하 {len(down_q)} · "
                   f"인상 {len(up_q)} · 내려감 {len(gone_q)})")
        out += _bullets(new_q, lambda q: f"🆕 {_q_label(q)} — {fmt_money(q['price'])}원")
        out += _bullets(down_q, lambda t: f"🔻 {_q_label(t[0])} — {fmt_money(t[1])}→{fmt_money(t[2])}원")
        out += _bullets(up_q, lambda t: f"🔺 {_q_label(t[0])} — {fmt_money(t[1])}→{fmt_money(t[2])}원")
        out += _bullets(gone_q, lambda q: f"⬇️ {_q_label(q)} — {fmt_money(q['price'])}원 내려감")

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
    deal_diff = diff_deals(before_deals, after_deals)
    quote_diff = diff_quotes(before_quotes, after_quotes)

    summary = build_summary(datetime.now(KST), deal_diff, quote_diff, failures)
    print("\n" + "=" * 50 + "\n" + summary + "\n" + "=" * 50)

    if args.no_notify:
        print("\n--no-notify: Discord 전송 생략")
    else:
        send_discord(summary)


if __name__ == "__main__":
    main()
