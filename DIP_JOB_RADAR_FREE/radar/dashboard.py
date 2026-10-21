"""Local-only, read-only dashboard; no third-party UI dependencies.

Run: python -m radar.dashboard    then open http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from radar.database import RadarDB as JobDB
from radar.private_state import PrivateState

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "dashboard/index.html"


class Dashboard(BaseHTTPRequestHandler):
    def _reply(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self._reply(200, FRONTEND.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/app.js":
            self._reply(200, (ROOT / "dashboard/app.js").read_bytes(), "text/javascript; charset=utf-8")
            return
        if path == "/api/jobs" or path == "/api/stats":
            db = JobDB(ROOT / "data/jobs.sqlite3")
            try:
                if path == "/api/stats":
                    data = db.stats(days=7)
                else:
                    data = db.list_opportunities(limit=700)
                    try:
                        private = PrivateState(ROOT / "data/private_state.enc")
                        for job in data:
                            job["status"] = private.get_feedback(job["fingerprint"])
                    except RuntimeError:
                        for job in data:
                            job["status"] = ""
            finally:
                db.close()
            self._reply(200, json.dumps(data).encode(), "application/json; charset=utf-8")
            return
        self._reply(404, b"Not found", "text/plain")

    def log_message(self, format, *args):
        return


def main():
    port = int(os.getenv("RADAR_DASHBOARD_PORT", "8765"))
    # Never bind to 0.0.0.0 or deploy this local dashboard as public production website.
    server = ThreadingHTTPServer(("127.0.0.1", port), Dashboard)
    print(f"Local-only dashboard: http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
