#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地自测：用一个极简 HTTP mock 来验证 MagicLLM/esp32_server.py 的上报端口与路径。

不依赖真实 ESP32。
- mock 服务监听 8083（可用环境变量覆盖）。
- 然后调用 esp32_server.trigger_key_moment(1)，期望命中 mock 的 /api/mark_moment。

用法（可选）：
    python3 MagicLLM/test_esp32_trigger_mock.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# 确保可从仓库根目录直接运行（无需 pip install）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _make_handler(state: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                payload = {"_raw": raw.decode("utf-8", errors="ignore")}

            state["path"] = self.path
            state["payload"] = payload

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{\"ok\": true}")

        def log_message(self, format, *args):
            # 安静一点，避免刷屏
            return

    return Handler


def main() -> int:
    # 让被测代码固定只打到本 mock
    os.environ["ONEKEY_WEB_PORTS"] = os.environ.get("ONEKEY_WEB_PORTS", "8083")
    os.environ["ONEKEY_MARK_MOMENT_PATH"] = os.environ.get("ONEKEY_MARK_MOMENT_PATH", "/api/mark_moment")

    host = "127.0.0.1"
    port = int(os.environ["ONEKEY_WEB_PORTS"].split(",")[0].strip())

    state: dict = {}

    httpd = HTTPServer((host, port), _make_handler(state))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    # 等待端口起来
    time.sleep(0.2)

    from MagicLLM.esp32_server import trigger_key_moment

    trigger_key_moment("1")

    httpd.shutdown()
    t.join(timeout=1.0)

    expected_path = os.environ["ONEKEY_MARK_MOMENT_PATH"]
    if state.get("path") != expected_path:
        print(f"FAIL: expected path={expected_path}, got={state.get('path')}")
        return 1

    note = (state.get("payload") or {}).get("note")
    if not note:
        print(f"FAIL: payload missing note, got={state.get('payload')}")
        return 1

    print("PASS: esp32_server.trigger_key_moment hit mock successfully")
    print(f"  path: {state.get('path')}")
    print(f"  payload: {state.get('payload')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
