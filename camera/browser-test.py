#!/usr/bin/env python3
"""Serve a temporary localhost-only camera preview; record only frame counters."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import time

page = Path(__file__).with_suffix('.html').read_bytes()
result = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        global result
        if self.path != '/result' or int(self.headers.get('Content-Length', 0)) > 1024:
            self.send_error(400)
            return
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        result = {key: data[key] for key in ['ok', 'frames', 'width', 'height', 'error'] if key in data}
        print(json.dumps(result), flush=True)
        self.send_response(204)
        self.end_headers()


with HTTPServer(('127.0.0.1', 0), Handler) as server:
    server.timeout = 1
    url = f'http://127.0.0.1:{server.server_port}/'
    subprocess.Popen(['firefox', '--new-window', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('Local Firefox test opened. Click Start camera test and allow camera access.', flush=True)
    deadline = time.monotonic() + 180
    while result is None and time.monotonic() < deadline:
        server.handle_request()
    if result is None:
        raise SystemExit('Browser test not completed within 180 seconds')
    if not result.get('ok') or result.get('frames', 0) < 30:
        raise SystemExit('Browser did not report successful frame presentation')
    print('PASS Firefox getUserMedia and 30 presented frames; camera auto-stops after 20 seconds.', flush=True)
