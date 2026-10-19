#!/usr/bin/env python3
"""User-timed microphone test; only numerical results leave browser memory."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from check import check, endpoints

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fresh-profile', action='store_true', help='isolated Firefox process; temporary profile is removed afterward')
args = parser.parse_args()
profile = None
browser = None
if check():
    raise SystemExit('Audio safety verification must pass before browser playback')
sinks = endpoints('sinks')
if len(sinks) != 1:
    raise SystemExit('Expected one internal analog output')
sink = sinks[0]['name']
subprocess.run(['pactl', 'set-sink-mute', sink, '1'], check=True)
subprocess.run(['pactl', 'set-sink-volume', sink, '40%'], check=True)
subprocess.run(['pactl', 'set-sink-mute', sink, '0'], check=True)
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
        result = {key: data[key] for key in ['ok', 'voice_confirmed', 'sampleRate', 'frames', 'peakDb', 'rmsDb', 'clipped'] if key in data}
        print(json.dumps(result), flush=True)
        self.send_response(204)
        self.end_headers()


try:
    with HTTPServer(('127.0.0.1', 0), Handler) as server:
        server.timeout = 1
        command = ['firefox']
        if args.fresh_profile:
            parent = Path.home() / 'snap/firefox/common'
            parent.mkdir(parents=True, exist_ok=True)
            profile = tempfile.mkdtemp(prefix='t1-microphone-test-', dir=parent)
            command += ['--no-remote', '--profile', profile]
        command += ['--new-window', f'http://127.0.0.1:{server.server_port}/']
        browser = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        print('Firefox microphone test opened: Record, Replay, then Confirm. Eight-minute limit.', flush=True)
        deadline = time.monotonic() + 480
        while result is None and time.monotonic() < deadline:
            server.handle_request()
        if result is None or not result.get('voice_confirmed'):
            raise SystemExit('Intelligible voice not confirmed in browser test')
        print('PASS user confirmed intelligible microphone replay; recording cleared.', flush=True)
finally:
    subprocess.run(['pactl', 'set-sink-mute', sink, '1'])
    subprocess.run(['pactl', 'set-sink-volume', sink, '2%'])
    if profile:
        if browser and browser.poll() is None:
            os.killpg(browser.pid, signal.SIGTERM)
            try:
                browser.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(browser.pid, signal.SIGKILL)
                browser.wait()
        shutil.rmtree(profile)
