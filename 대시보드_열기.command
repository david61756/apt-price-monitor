#!/bin/bash
# 더블클릭하면 로컬 순서저장 서버를 켜고 브라우저에서 대시보드(localhost:8787)를 엽니다.
# 이 창에서 자동 저장이 동작합니다('순서 저장' → 자동 커밋·공유). 종료: 이 창에서 Ctrl+C.
cd "$HOME/apt-price-monitor" || exit 1
export PATH="/opt/anaconda3/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
( sleep 1.3; open "http://localhost:8787/" ) &
echo "대시보드를 http://localhost:8787/ 에서 엽니다. 종료하려면 Ctrl+C."
python3 order_server.py
