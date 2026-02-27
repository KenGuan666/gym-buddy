from __future__ import annotations

import asyncio
import os
import traceback
from http.server import BaseHTTPRequestHandler

from gym_supervisor.server import send_weekly_nudges_once


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

        try:
            asyncio.run(send_weekly_nudges_once())
        except Exception as exc:
            tb = traceback.format_exc()
            print(tb)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"failed: {exc!r}\n{tb}".encode("utf-8", errors="replace"))
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self) -> None:
        self.do_GET()
