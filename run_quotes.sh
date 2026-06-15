#!/bin/bash
# 네이버 호가 자동 수집 → 커밋 → 푸시. launchd(매일) 또는 수동(`bash run_quotes.sh`) 실행.
set -u
PROJ="$HOME/apt-price-monitor"
cd "$PROJ" || exit 1
export PATH="/opt/anaconda3/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LOG="$PROJ/logs/quotes.log"
mkdir -p "$PROJ/logs"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 네트워크 준비 대기: 절전에서 깨어난 직후 Wi-Fi가 아직 안 올라온 상태로 실행되는 것 방지.
# GitHub 접속이 될 때까지 최대 ~120초 대기. 끝내 안 되면 이번 회차는 건너뜀(데이터 보존).
wait_net() { for _ in $(seq 1 24); do curl -sf -m 5 -o /dev/null https://github.com && return 0; sleep 5; done; return 1; }
if ! wait_net; then echo "$(ts) 네트워크 미연결 — 이번 실행 건너뜀(데이터 보존)" >> "$LOG"; exit 0; fi

# 상호배제 락: run_quotes ↔ sync_quotes 동시 실행 방지(동일 .naver_profile/Chromium 충돌·push 경쟁)
LOCKDIR="$PROJ/logs/.run.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  if find "$LOCKDIR" -maxdepth 0 -mmin +30 2>/dev/null | grep -q .; then
    rmdir "$LOCKDIR" 2>/dev/null; mkdir "$LOCKDIR" 2>/dev/null \
      || { echo "$(ts) 락 획득 실패 — skip" >> "$LOG"; exit 0; }
  else
    echo "$(ts) 이미 실행 중 — skip" >> "$LOG"; exit 0
  fi
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

echo "===== $(ts) 호가 수집 시작 =====" >> "$LOG"

# 원격(Actions 매매) 반영. 실제 rebase 충돌일 때만 생성물 원격 우선으로 해소(네트워크 실패와 구분).
if ! git pull --rebase --autostash origin main >> "$LOG" 2>&1; then
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    echo "$(ts) rebase 충돌 — 생성물 원격 우선 해소" >> "$LOG"
    git checkout --ours -- docs/index.html quotes_state.json state.json config.yaml >> "$LOG" 2>&1 || true
    git add docs/index.html quotes_state.json state.json config.yaml >> "$LOG" 2>&1 || true
    git rebase --continue >> "$LOG" 2>&1 || git rebase --abort >> "$LOG" 2>&1
  else
    echo "$(ts) git pull 실패(네트워크 등, 충돌 아님) — 이번 실행 건너뜀" >> "$LOG"; exit 0
  fi
fi

python3 quotes_monitor.py >> "$LOG" 2>&1
echo "quotes_monitor 종료코드: $?" >> "$LOG"

git add quotes_state.json docs/index.html >> "$LOG" 2>&1
if git diff --cached --quiet; then
  echo "변경 없음 — 커밋 생략" >> "$LOG"
else
  git commit -m "chore: 호가 자동 갱신 ($(date '+%Y-%m-%d %H:%M') KST)" >> "$LOG" 2>&1
  if ! git push origin main >> "$LOG" 2>&1; then
    git pull --rebase --autostash origin main >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1 || echo "$(ts) PUSH 실패 — 수동 확인 필요" >> "$LOG"
  fi
fi
echo "===== $(ts) 완료 =====" >> "$LOG"
