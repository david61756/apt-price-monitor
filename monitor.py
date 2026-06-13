#!/usr/bin/env python3
"""아파트 매매 실거래가 자동 모니터링.

국토교통부 '아파트 매매 실거래가 상세 자료' API(RTMSDataSvcAptTradeDev)로
관심 단지의 신규 거래를 감지해 텔레그램으로 알리고 state.json에 누적 기록한다.

사용법:
    python monitor.py                # 조회 → 신규 감지 → 알림 → state/대시보드 갱신
    python monitor.py --dry-run      # 알림/저장 없이 감지 결과만 출력
    python monitor.py --no-notify    # 알림 없이 저장만
    python monitor.py --backfill 24  # 과거 24개월치 데이터를 한 번에 수집(알림 없음)
"""
import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

from dashboard import render_dashboard
from lawd import resolve_lawd_cd
from matching import match_complex

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
STATE_PATH = BASE_DIR / "state.json"
DASHBOARD_PATH = BASE_DIR / "docs" / "index.html"

API_URL = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev"
    "/getRTMSDataSvcAptTradeDev"
)
# data.go.kr 게이트웨이가 기본(curl/requests) User-Agent를 차단하므로 필수
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
}
KST = timezone(timedelta(hours=9))
PAGE_SIZE = 1000
MAX_RETRIES = 3


# ---------------------------------------------------------------- env/config

def load_env():
    """간단한 .env 로더 (기존 환경변수는 덮어쓰지 않음)."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    complexes = cfg.get("complexes") or []
    if not complexes:
        sys.exit("config.yaml에 complexes가 비어 있습니다.")
    for c in complexes:
        if not c.get("name"):
            sys.exit("config.yaml: 각 단지에 name이 필요합니다.")
        if c.get("lawd_cd"):
            c["lawd_cd"] = str(c["lawd_cd"]).zfill(5)
        elif c.get("region"):
            c["lawd_cd"] = resolve_lawd_cd(c["region"])
        else:
            sys.exit(f"config.yaml: '{c['name']}'에 region 또는 lawd_cd가 필요합니다.")
        c["match"] = c.get("match") or [c["name"]]
        c["areas"] = [int(a) for a in (c.get("areas") or [])]
        c["naver_id"] = str(c["naver_id"]).strip() if c.get("naver_id") else None
    cfg["options"] = cfg.get("options") or {}
    naver = cfg.get("naver") or {}
    naver.setdefault("trade_types", ["A1"])
    naver.setdefault("notify", True)
    cfg["naver"] = naver
    return cfg


# ----------------------------------------------------------------- API 호출

def fetch_month(service_key, lawd_cd, deal_ymd):
    """한 지역·한 달의 전체 거래를 페이지네이션하며 수집."""
    records, page = [], 1
    while True:
        params = {
            "serviceKey": service_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
        }
        root = _request_with_retry(params)
        body = root.find("body")
        if body is None:
            raise RuntimeError(f"API 응답에 body가 없습니다: {ET.tostring(root, encoding='unicode')[:300]}")
        items = body.find("items")
        if items is not None:
            for item in items.findall("item"):
                rec = _parse_item(item, lawd_cd)
                if rec:
                    records.append(rec)
        total = int(body.findtext("totalCount") or 0)
        if page * PAGE_SIZE >= total:
            break
        page += 1
    return records


def _request_with_retry(params):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(API_URL, params=params, headers=HTTP_HEADERS, timeout=30)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            # data.go.kr 게이트웨이 에러 (인증키 오류 등)
            if root.tag == "OpenAPI_ServiceResponse":
                code = root.findtext(".//returnReasonCode") or "?"
                msg = root.findtext(".//returnAuthMsg") or "unknown"
                raise RuntimeError(f"data.go.kr 게이트웨이 에러 [{code}] {msg}")
            result_code = root.findtext(".//resultCode") or ""
            if result_code not in ("000", "00", "03"):  # 03 = No Data
                msg = root.findtext(".//resultMsg") or ""
                raise RuntimeError(f"API 에러 [{result_code}] {msg}")
            return root
        except (requests.RequestException, ET.ParseError, RuntimeError) as e:
            last_err = e
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"  ! 호출 실패({e}), {wait}초 후 재시도 {attempt}/{MAX_RETRIES}")
                time.sleep(wait)
    raise RuntimeError(f"API 호출 {MAX_RETRIES}회 실패: {last_err}")


def _parse_item(item, lawd_cd):
    def g(tag):
        return (item.findtext(tag) or "").strip()

    try:
        amount = int(g("dealAmount").replace(",", "") or 0)
        date = "{:04d}-{:02d}-{:02d}".format(
            int(g("dealYear")), int(g("dealMonth")), int(g("dealDay")))
        area = float(g("excluUseAr") or 0)
    except ValueError:
        return None
    return {
        "apt_nm": g("aptNm"),
        "apt_seq": g("aptSeq"),
        "umd_nm": g("umdNm"),
        "area": area,
        "floor": g("floor"),
        "amount": amount,            # 만원
        "date": date,                # 계약일 YYYY-MM-DD
        "build_year": g("buildYear"),
        "dealing_gbn": g("dealingGbn"),
        "cancelled": g("cdealType") == "O",
        "cancel_date": g("cdealDay"),
        "lawd_cd": lawd_cd,
    }


def deal_id(rec):
    return "|".join([rec["apt_seq"], rec["date"], f"{rec['area']:g}",
                     rec["floor"] or "-", str(rec["amount"])])


# -------------------------------------------------------------- 매칭/diff

def target_months(now_kst, months_back=1):
    """이번 달 + 과거 N개월 (신고 지연 대비)."""
    months, y, m = [], now_kst.year, now_kst.month
    for _ in range(months_back + 1):
        months.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return months


def find_prev_deal(all_deals, rec):
    """같은 단지·같은 면적대(정수 ㎡)에서 이 계약일 직전의 유효 거래."""
    band = int(rec["area"])
    candidates = [
        d for d in all_deals
        if d["apt_seq"] == rec["apt_seq"]
        and int(d["area"]) == band
        and not d.get("cancelled")
        and d["date"] < rec["date"]
    ]
    return max(candidates, key=lambda d: d["date"]) if candidates else None


# -------------------------------------------------------------- 알림 포맷

def fmt_money(man):
    """만원 → '7억 7,000만' 형식."""
    sign = "-" if man < 0 else ""
    man = abs(man)
    eok, rest = divmod(man, 10000)
    if eok and rest:
        return f"{sign}{eok}억 {rest:,}만"
    if eok:
        return f"{sign}{eok}억"
    return f"{sign}{rest:,}만"


def build_message(complex_name, rec, prev):
    lines = [
        "🏠 <b>신규 실거래</b>",
        f"<b>{rec['apt_nm']}</b> ({rec['umd_nm']})",
        f"전용 {rec['area']:g}㎡ · {rec['floor'] or '?'}층",
        f"💰 <b>{fmt_money(rec['amount'])}원</b>",
        f"계약일 {rec['date']}" + (f" · {rec['dealing_gbn']}" if rec["dealing_gbn"] else ""),
    ]
    if prev:
        diff = rec["amount"] - prev["amount"]
        pct = diff / prev["amount"] * 100
        if diff > 0:
            arrow = f"🔺 +{fmt_money(diff)} (+{pct:.1f}%)"
        elif diff < 0:
            arrow = f"🔻 {fmt_money(diff)} ({pct:.1f}%)"
        else:
            arrow = "⏸ 보합"
        lines.append(
            f"직전 {int(prev['area'])}㎡대 거래 {fmt_money(prev['amount'])}원"
            f" ({prev['date']}) 대비 {arrow}")
    else:
        lines.append("직전 동일 평형 거래 기록 없음 (비교 불가)")
    return "\n".join(lines)


def build_cancel_message(rec):
    return "\n".join([
        "❌ <b>거래 해제</b>",
        f"<b>{rec['apt_nm']}</b> 전용 {rec['area']:g}㎡ · {rec['floor'] or '?'}층",
        f"{fmt_money(rec['amount'])}원 (계약일 {rec['date']})",
        f"해제일 {rec['cancel_date'] or '?'}",
    ])


def send_telegram(messages):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠ TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 — 콘솔 출력으로 대체합니다.")
        for m in messages:
            print("-" * 40)
            print(m.replace("<b>", "").replace("</b>", ""))
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # 4096자 제한 → 여러 건이면 묶되 한도 내에서 분할 전송
    chunks, cur = [], ""
    for m in messages:
        if cur and len(cur) + len(m) + 2 > 3500:
            chunks.append(cur)
            cur = m
        else:
            cur = f"{cur}\n\n{m}" if cur else m
    if cur:
        chunks.append(cur)
    for chunk in chunks:
        resp = requests.post(url, json={
            "chat_id": chat_id, "text": chunk,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }, timeout=30)
        if not resp.ok:
            print(f"⚠ 텔레그램 전송 실패: {resp.status_code} {resp.text[:200]}")
        time.sleep(0.5)


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="알림/저장 없이 감지만")
    ap.add_argument("--no-notify", action="store_true", help="알림 없이 저장만")
    ap.add_argument("--backfill", type=int, metavar="N",
                    help="이번 달 포함 과거 N개월치를 한 번에 수집 (알림 없음)")
    args = ap.parse_args()

    load_env()
    service_key = os.environ.get("MOLIT_API_KEY")
    if not service_key:
        sys.exit("MOLIT_API_KEY가 없습니다. .env 또는 환경변수로 설정하세요.")

    cfg = load_config()
    months_back = args.backfill if args.backfill else int(cfg["options"].get("months_back", 1))
    months = target_months(datetime.now(KST), months_back)
    if args.backfill:
        print(f"백필 모드: {months[-1]} ~ {months[0]} ({len(months)}개월) 수집, 알림 없음")

    first_run = not STATE_PATH.exists()
    state = {"deals": {}}
    if not first_run:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    known = state.setdefault("deals", {})

    # 지역코드별로 한 번만 조회 (여러 단지가 같은 구에 있어도 중복 호출 없음)
    lawd_cds = sorted({c["lawd_cd"] for c in cfg["complexes"]})
    fetched = {}  # deal_id -> record (해제 레코드가 원거래와 중복되면 해제 우선)
    for lawd_cd in lawd_cds:
        for ymd in months:
            print(f"조회: LAWD_CD={lawd_cd} DEAL_YMD={ymd} ...", end=" ")
            recs = fetch_month(service_key, lawd_cd, ymd)
            print(f"{len(recs)}건")
            for r in recs:
                rid = deal_id(r)
                if rid not in fetched or r["cancelled"]:
                    fetched[rid] = r

    # 관심 단지 매칭 (단지별 매칭 수 진단)
    matched = {}
    per_complex = {}
    for c in cfg["complexes"]:
        cnt = 0
        for rid, r in fetched.items():
            if match_complex(r, c):
                matched[rid] = {**r, "complex": c["name"]}
                cnt += 1
        per_complex[c["name"]] = cnt

    print("\n=== 단지별 조회 기간 내 매칭 ===")
    for c in cfg["complexes"]:
        n = per_complex[c["name"]]
        flag = "  ⚠ 0건 — 단지명(match)·면적(areas) 확인 필요" if n == 0 else ""
        print(f"  {n:4d}건  {c['name']}  "
              f"[{c['lawd_cd']} / match={c['match']} / areas={c['areas'] or '전체'}]{flag}")

    # 신규/해제 diff
    new_deals, cancelled_deals = [], []
    for rid, r in sorted(matched.items(), key=lambda kv: kv[1]["date"]):
        if rid not in known:
            known[rid] = {**r, "first_seen": datetime.now(KST).isoformat(timespec="seconds")}
            if not r["cancelled"]:
                new_deals.append(r)
        elif r["cancelled"] and not known[rid].get("cancelled"):
            known[rid].update(cancelled=True, cancel_date=r["cancel_date"])
            cancelled_deals.append(r)

    print(f"\n관심단지 거래 {len(matched)}건 중 신규 {len(new_deals)}건, "
          f"해제 {len(cancelled_deals)}건")

    # 알림 메시지 생성 (직전 거래 비교는 전체 기록 기준)
    all_known = list(known.values())
    messages = []
    for r in new_deals:
        prev_pool = [d for d in all_known if deal_id(d) != deal_id(r)]
        messages.append(build_message(r["complex"], r, find_prev_deal(prev_pool, r)))
    if cfg["options"].get("notify_cancellations", True):
        messages += [build_cancel_message(r) for r in cancelled_deals]

    if first_run:
        print("ℹ 최초 실행: 기존 거래를 기준선으로 저장만 하고 알림은 보내지 않습니다.")
    elif args.backfill:
        print(f"ℹ 백필: 신규 {len(new_deals)}건을 알림 없이 저장합니다.")
    elif messages and not (args.dry_run or args.no_notify):
        send_telegram(messages)
    elif messages:
        print("\n[알림 미리보기]")
        for m in messages:
            print("-" * 40)
            print(m.replace("<b>", "").replace("</b>", ""))

    if args.dry_run:
        print("\n--dry-run: state.json/대시보드를 갱신하지 않았습니다.")
        return

    # 관심단지에서 빠진(현재 config에 매칭 안 되는) 옛 거래는 정리해 state를 동기화
    before = len(known)
    known = {rid: d for rid, d in known.items()
             if any(match_complex(d, c) for c in cfg["complexes"])}
    state["deals"] = known
    if before - len(known):
        print(f"정리: 현재 관심단지에 없는 거래 {before - len(known)}건 제거")

    state["last_run"] = datetime.now(KST).isoformat(timespec="seconds")
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    DASHBOARD_PATH.parent.mkdir(exist_ok=True)
    # 호가 데이터가 있으면 함께 렌더(읽기만 — 매매 워크플로에 영향 없음)
    try:
        from quotes import load_quotes_state, QUOTES_PATH
        qstate = load_quotes_state(QUOTES_PATH) if QUOTES_PATH.exists() else None
    except Exception:
        qstate = None
    render_dashboard(state, cfg, DASHBOARD_PATH, quotes_state=qstate)
    print(f"state.json 저장 (관심단지 누적 {len(known)}건), 대시보드 갱신: {DASHBOARD_PATH}")


if __name__ == "__main__":
    main()
