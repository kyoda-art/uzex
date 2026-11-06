"""Monitoring uchun oddiy HTTP javob: UptimeRobot '/' ga so'rov yuboradi, 200 OK qaytadi."""
from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)


class _Handler(BaseHTTPRequestHandler):
    def _ok(self):
        body = "UZEX bot ishlayapti".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_GET = _ok
    do_HEAD = _ok

    def log_message(self, fmt, *args):  # monitor so'rovlari logni to'ldirmasin
        return


def start_health_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Health server: port %d", port)
    return server
