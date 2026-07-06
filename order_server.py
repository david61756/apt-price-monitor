#!/usr/bin/env python3
"""로컬 대시보드 서버 + 카드 순서 자동 저장.

실행:
    python3 order_server.py
    → 브라우저에서 http://localhost:8787/ 로 대시보드 열기.

대시보드에서 '💾 순서 저장'을 누르면(로컬 서버로 접속한 경우) 이 서버가
docs/order.json 을 기록하고 자동으로 git 커밋·푸시(.env의 GITHUB_TOKEN 사용)해
모든 기기에 공유합니다. GitHub Pages(github.io)로 접속했을 땐 클립보드 폴백
(→ bash save_order.sh)으로 동작합니다.
"""
import base64
import json
import os
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

BASE = Path(__file__).resolve().parent
DOCS = BASE / "docs"
PORT = 8787


def load_token():
    env = BASE / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("GITHUB_TOKEN="):
            return (line.split("=", 1)[1].strip().strip("'\"")) or None
    return None


def git_env():
    env = os.environ.copy()
    tok = load_token()
    if tok:
        hdr = "AUTHORIZATION: basic " + base64.b64encode(
            f"x-access-token:{tok}".encode()).decode()
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
        env["GIT_CONFIG_VALUE_0"] = hdr
    return env


def commit_push():
    env = git_env()

    def run(*args):
        return subprocess.run(["git", *args], cwd=str(BASE), env=env,
                              capture_output=True, text=True)

    run("add", "docs/order.json")
    if run("diff", "--cached", "--quiet").returncode == 0:
        return True, "변경 없음(순서 동일)"
    run("commit", "-q", "-m", "chore: 대시보드 카드 순서 변경(order.json)")
    run("pull", "--rebase", "--autostash", "origin", "main")
    if run("push", "origin", "main").returncode == 0:
        return True, "저장·공유 완료"
    return False, "push 실패 — 네트워크/토큰 확인"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(DOCS), **k)

    def do_POST(self):
        if self.path.split("?")[0] != "/save-order":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw)
            assert isinstance(data, dict) and ("complexes" in data or "regions" in data)
        except Exception:
            self._json(400, {"ok": False, "msg": "잘못된 순서 데이터"})
            return
        (DOCS / "order.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        ok, msg = commit_push()
        self._json(200 if ok else 500, {"ok": ok, "msg": msg})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if self.path.split("?")[0].rstrip("/").endswith("order.json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"대시보드(자동 순서저장): http://localhost:{PORT}/")
    print("종료: Ctrl+C")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
