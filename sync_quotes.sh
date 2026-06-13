#!/bin/bash
# 원격(GitHub) config.yaml이 바뀌면(=대시보드 단지관리에서 저장하면) 호가를 자동 갱신.
# launchd가 짧은 주기로 호출. config 변경이 없으면 git fetch만 하고 즉시 종료(가벼움).
set -u
PROJ="$HOME/apt-price-monitor"
cd "$PROJ" || exit 1
export PATH="/opt/anaconda3/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LOG="$PROJ/logs/sync.log"
mkdir -p "$PROJ/logs"

git fetch origin main -q 2>>"$LOG" || exit 0
LOCAL=$(git rev-parse HEAD:config.yaml 2>/dev/null)
REMOTE=$(git rev-parse origin/main:config.yaml 2>/dev/null)
[ -z "$REMOTE" ] && exit 0
[ "$LOCAL" = "$REMOTE" ] && exit 0      # config 변경 없음 → 종료

echo "===== $(date '+%Y-%m-%d %H:%M:%S') config 변경 감지 → 호가 동기화 =====" >> "$LOG"
git pull --rebase --autostash >> "$LOG" 2>&1
python3 quotes_monitor.py >> "$LOG" 2>&1
echo "quotes_monitor 종료코드: $?" >> "$LOG"
git add quotes_state.json docs/index.html >> "$LOG" 2>&1
if git diff --cached --quiet; then
  echo "변경 없음 — 커밋 생략" >> "$LOG"
else
  git commit -m "chore: 단지 변경 반영 호가 동기화 ($(date '+%Y-%m-%d %H:%M') KST)" >> "$LOG" 2>&1
  git push >> "$LOG" 2>&1 || { git pull --rebase --autostash >> "$LOG" 2>&1; git push >> "$LOG" 2>&1; }
fi
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 동기화 완료 =====" >> "$LOG"
