"""Small MJPEG preview server with independent live/job channels."""
from http import server
import threading
import time
from urllib.parse import parse_qs, urlsplit

import cv2


class _State:
    def __init__(self):
        self.condition = threading.Condition()
        self.jpeg_by_channel = {}


class _Handler(server.BaseHTTPRequestHandler):
    state = None

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path in ('/', '/health'):
            body = b'Border Sentinel camera preview OK'
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path != '/stream.mjpg':
            self.send_error(404)
            return

        query = parse_qs(parsed.query)
        channel = query.get('job', ['live'])[0] or 'live'
        # Job IDs are UUIDs; keep the channel constrained so arbitrary memory
        # keys cannot be created by a browser request.
        if channel != 'live' and len(channel) > 80:
            self.send_error(400, 'Invalid preview channel')
            return

        self.send_response(200)
        self.send_header('Age', '0')
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.end_headers()

        try:
            while True:
                with self.state.condition:
                    jpeg = self.state.jpeg_by_channel.get(channel)
                    if jpeg is None:
                        self.state.condition.wait(timeout=1.0)
                        jpeg = self.state.jpeg_by_channel.get(channel)

                if jpeg is None:
                    continue
                self.wfile.write(b'--frame\r\n')
                self.wfile.write(b'Content-Type: image/jpeg\r\n')
                self.wfile.write(f'Content-Length: {len(jpeg)}\r\n\r\n'.encode())
                self.wfile.write(jpeg)
                self.wfile.write(b'\r\n')
                self.wfile.flush()
                time.sleep(0.03)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_args):
        return


class PreviewServer:
    def __init__(self, host='0.0.0.0', port=8001):
        self.state = _State()
        handler = type('PreviewHandler', (_Handler,), {'state': self.state})
        self.httpd = server.ThreadingHTTPServer((host, port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def publish(self, frame, channel='live'):
        ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return
        with self.state.condition:
            self.state.jpeg_by_channel[channel] = encoded.tobytes()
            self.state.condition.notify_all()

    def close_channel(self, channel):
        with self.state.condition:
            self.state.jpeg_by_channel.pop(channel, None)
            self.state.condition.notify_all()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
