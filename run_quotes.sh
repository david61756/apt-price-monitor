#!/bin/bash
# 네이버 호가 자동 수집 → 커밋 → 푸시. launchd(매일) 또는 수동(`bash run_quotes.sh`)으로 실행.
set -u
PROJ="$HOME/apt-price-monitor"
cd "$PROJ" || exit 1
export PATH="/opt/anaconda3/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LOG="$PROJ/logs/quotes.log"
mkdir -p "$PROJ/logs"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
echo "===== $(ts) 호가 수집 시작 =====" >> "$LOG"

# 1) 매매(Actions) 최신 커밋 반영
git pull --rebase --autostash >> "$LOG" 2>&1

# 2) 수집 (Playwright 자동 로그인 — 토큰 입력 불필요)
python3 quotes_monitor.py >> "$LOG" 2>&1
echo "quotes_monitor 종료코드: $?" >> "$LOG"

# 3) 변경분만 커밋·푸시 (실패 시 1회 재시도)
git add quotes_state.json docs/index.html >> "$LOG" 2>&1
if git diff --cached --quiet; then
  echo "변경 없음 — 커밋 생략" >> "$LOG"
else
  git commit -m "chore: 호가 자동 갱신 ($(date '+%Y-%m-%d %H:%M') KST)" >> "$LOG" 2>&1
  git push >> "$LOG" 2>&1 || { git pull --rebase --autostash >> "$LOG" 2>&1; git push >> "$LOG" 2>&1; }
fi
echo "===== $(ts) 완료 =====" >> "$LOG"
