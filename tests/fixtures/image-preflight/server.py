"""Synthetic container for exercising the preflight, not a production backend."""
import http.server
import json
import os
import signal
import socket
import sys
import threading
import time

secret = os.environ.get('SIGNING_KEY', '')
if len(secret) < 32 or secret in {'change-me', 'secret', 'admin'}:
    print(json.dumps({'time':'fixture', 'logger':'config', 'level':'error', 'msg':'configuration: SIGNING_KEY'}), flush=True)
    sys.exit(2)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if os.environ.get('NOISY') == '1':
            print(json.dumps({'logger':'http', 'level':'info', 'msg':fmt % args}), flush=True)
    def do_GET(self):
        status, body = 200, 'preflight-backend'
        if self.path.startswith('/health/ready'):
            try:
                with socket.create_connection(('db', 5432), timeout=.2): pass
                body = '{"status":"ready"}'
            except OSError:
                status, body = 503, '{"status":"not ready"}'
        elif self.path.startswith('/health/live'): body = '{"status":"ok"}'
        elif self.path.startswith('/metrics'):
            body = '# TYPE app_build_info gauge\napp_build_info{version="1.3.2",commit="fixture"} 1\n'
        elif self.path.startswith('/api/slow'):
            time.sleep(3)
        self.send_response(status); self.end_headers()
        try: self.wfile.write(body.encode())
        except BrokenPipeError: pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.send_response(200); self.end_headers(); self.wfile.write(b'uploaded')
server = http.server.ThreadingHTTPServer(('0.0.0.0', 8000), Handler)
def stop(*_): threading.Thread(target=server.shutdown).start()
signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
server.serve_forever(); server.server_close()
