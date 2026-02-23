from __future__ import annotations

import asyncio
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

from gym_supervisor.server import send_morning_greeting_once


def _authorized(headers) -> bool:
    cron_secret = os.getenv("CRON_SECRET", "").strip()
    if not cron_secret:
        return headers.get("x-vercel-cron") == "1"
    auth_header = headers.get("authorization", "")
    return auth_header == f"Bearer {cron_secret}"


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not _authorized(self.headers):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return

        now_pt = datetime.now(ZoneInfo("America/Los_Angeles"))
        if now_pt.hour != 8:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"skipped (not 8am Pacific)")
            return

        try:
            asyncio.run(send_morning_greeting_once())
        except Exception:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"failed")
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"sent")

    def do_POST(self) -> None:
        self.do_GET()
