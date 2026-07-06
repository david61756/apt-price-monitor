#!/bin/bash
# 대시보드 '순서 저장'으로 클립보드에 복사된 순서(JSON)를 docs/order.json에 반영·커밋·푸시.
# → order.json은 GitHub Pages로 서빙되어 모든 기기에서 공유됨(다른 기기는 '🔄 공유순서 불러오기').
# 저장(커밋)은 이 로컬 Mac에서만 수행(.env 토큰 사용, 브라우저 토큰 불필요).
set -u
PROJ="$HOME/apt-price-monitor"
cd "$PROJ" || exit 1
export PATH="/opt/anaconda3/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# .env의 GitHub 토큰으로 인증(리모트 URL/.git/config에 토큰 안 남김)
gh_auth() {
  local t
  t=$(grep -E '^GITHUB_TOKEN=' "$PROJ/.env" 2>/dev/null | head -1 | cut -d= -f2-)
  t=${t%\"}; t=${t#\"}; t=${t%\'}; t=${t#\'}
  t=$(printf '%s' "$t" | tr -d '[:space:]')
  [ -z "$t" ] && return 0
  export GIT_CONFIG_COUNT=1
  export GIT_CONFIG_KEY_0="http.https://github.com/.extraheader"
  export GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$t" | base64 | tr -d '\n')"
}
gh_auth

CLIP=$(pbpaste)
printf '%s' "$CLIP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'complexes' in d or 'regions' in d" 2>/dev/null \
  || { echo "❌ 클립보드가 유효한 순서 JSON이 아닙니다. 대시보드에서 '💾 순서 저장'을 먼저 누르세요."; exit 1; }

mkdir -p docs
printf '%s' "$CLIP" > docs/order.json
git add docs/order.json
if git diff --cached --quiet; then echo "변경 없음 — 순서 동일"; exit 0; fi
git commit -q -m "chore: 대시보드 카드 순서 변경(order.json)"
git pull --rebase --autostash origin main >/dev/null 2>&1 || true
if git push origin main >/dev/null 2>&1; then
  echo "✅ 순서 저장·공유 완료 — 다른 기기는 '🔄 공유순서 불러오기' 또는 새로고침"
else
  echo "❌ push 실패 — 네트워크/토큰 확인"
fi
