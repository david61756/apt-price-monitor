#!/bin/bash
# 원격(GitHub) config.yaml이 바뀌면(=대시보드 단지관리 저장 시) 호가를 자동 갱신.
# launchd가 짧은 주기로 호출. 변경이 없으면 git fetch만 하고 즉시 종료(가벼움).
set -u
PROJ="$HOME/apt-price-monitor"
cd "$PROJ" || exit 1
export PATH="/opt/anaconda3/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LOG="$PROJ/logs/sync.log"
mkdir -p "$PROJ/logs"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 네트워크 준비 대기(wake 직후 Wi-Fi 지연 대비). 안 되면 조용히 종료 — 15분 뒤 다음 주기 재시도.
wait_net() { for _ in $(seq 1 12); do curl -sf -m 5 -o /dev/null https://github.com && return 0; sleep 5; done; return 1; }
wait_net || exit 0

git fetch origin main -q 2>>"$LOG" || { echo "$(ts) fetch 실패 — 종료" >> "$LOG"; exit 0; }
# 로컬 HEAD의 config과 원격 config을 비교: 다르면(대시보드에서 저장됨) 동기화
LOCAL=$(git rev-parse HEAD:config.yaml 2>/dev/null)
REMOTE=$(git rev-parse origin/main:config.yaml 2>/dev/null)
[ -z "$REMOTE" ] && exit 0
[ "$LOCAL" = "$REMOTE" ] && exit 0      # config 변경 없음 → 즉시 종료

# 변경 감지 → 락 획득 후 동기화 (run_quotes와 동일 락으로 상호배제)
LOCKDIR="$PROJ/logs/.run.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  if find "$LOCKDIR" -maxdepth 0 -mmin +30 2>/dev/null | grep -q .; then
    rmdir "$LOCKDIR" 2>/dev/null; mkdir "$LOCKDIR" 2>/dev/null || exit 0
  else
    echo "$(ts) 다른 작업 실행 중 — 다음 주기 재시도" >> "$LOG"; exit 0
  fi
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

echo "===== $(ts) config 변경 감지 → 호가 동기화 =====" >> "$LOG"
if ! git pull --rebase --autostash origin main >> "$LOG" 2>&1; then
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    echo "$(ts) rebase 충돌 — 생성물 원격 우선 해소" >> "$LOG"
    git checkout --ours -- docs/index.html quotes_state.json state.json config.yaml >> "$LOG" 2>&1 || true
    git add docs/index.html quotes_state.json state.json config.yaml >> "$LOG" 2>&1 || true
    git rebase --continue >> "$LOG" 2>&1 || git rebase --abort >> "$LOG" 2>&1
  else
    echo "$(ts) git pull 실패(네트워크 등) — 종료" >> "$LOG"; exit 0
  fi
fi

python3 quotes_monitor.py >> "$LOG" 2>&1
echo "quotes_monitor 종료코드: $?" >> "$LOG"
git add quotes_state.json docs/index.html >> "$LOG" 2>&1
if git diff --cached --quiet; then
  echo "변경 없음 — 커밋 생략" >> "$LOG"
else
  git commit -m "chore: 단지 변경 반영 호가 동기화 ($(date '+%Y-%m-%d %H:%M') KST)" >> "$LOG" 2>&1
  if ! git push origin main >> "$LOG" 2>&1; then
    git pull --rebase --autostash origin main >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1 || echo "$(ts) PUSH 실패 — 수동 확인 필요" >> "$LOG"
  fi
fi
echo "===== $(ts) 동기화 완료 =====" >> "$LOG"
