from __future__ import annotations

import asyncio
import json
import os
import traceback
from http.server import BaseHTTPRequestHandler

from gym_supervisor.server import process_telegram_update


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        header_secret = self.headers.get("x-telegram-bot-api-secret-token", "").strip()
        if expected_secret and header_secret != expected_secret:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return

        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"invalid json")
            return

        try:
            asyncio.run(process_telegram_update(payload))
        except Exception as exc:
            tb = traceback.format_exc()
            print(tb)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(
                f"processing error: {exc!r}\n{tb}".encode("utf-8", errors="replace")
            )
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"telegram webhook alive")
