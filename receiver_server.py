import base64
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '8765'))
UPLOAD_PATH = '/upload'
HEALTH_PATH = '/health'
LATEST_IMAGE_PATH = '/latest'
LATEST_META_PATH = '/latest.json'
ARCHIVE_DIR = os.environ.get('ARCHIVE_DIR', os.path.join(ROOT, 'archive'))
os.makedirs(ARCHIVE_DIR, exist_ok=True)

latest_image_file = os.path.join(ROOT, 'latest_capture.jpg')
latest_meta_file = os.path.join(ROOT, 'latest_capture.json')


def get_bind_address():
    return (HOST, PORT)


class ReceiverHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class ReceiverHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/receiver.html'):
            self.serve_file('receiver.html')
        elif path == HEALTH_PATH:
            self.send_json(200, {'status': 'ok'})
        elif path == LATEST_IMAGE_PATH:
            self.serve_image()
        elif path == LATEST_META_PATH:
            self.serve_json()
        else:
            self.send_error(404, 'Not found')

    def do_POST(self):
        if urlparse(self.path).path != UPLOAD_PATH:
            self.send_error(404, 'Not found')
            return

        content_length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_json(400, {'error': 'Invalid JSON'})
            return

        image_data = payload.get('image', '')
        if not isinstance(image_data, str) or ',' not in image_data:
            self.send_json(400, {'error': 'Missing image data'})
            return

        header, data = image_data.split(',', 1)
        if ';base64' in header:
            image_bytes = base64.b64decode(data)
        else:
            image_bytes = data.encode('utf-8')

        timestamp = payload.get('timestamp') or datetime.now(timezone.utc).isoformat()
        archive_name = f"capture_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        archive_path = os.path.join(ARCHIVE_DIR, archive_name)

        with open(latest_image_file, 'wb') as handle:
            handle.write(image_bytes)

        with open(archive_path, 'wb') as handle:
            handle.write(image_bytes)

        meta = {
            'timestamp': timestamp,
            'tab_id': payload.get('tab_id'),
            'window_id': payload.get('window_id'),
            'url': payload.get('url', ''),
            'title': payload.get('title', ''),
            'archive_path': archive_path,
            'archive_name': archive_name,
        }

        with open(latest_meta_file, 'w', encoding='utf-8') as handle:
            json.dump(meta, handle, indent=2)

        self.send_json(200, {'status': 'ok', 'saved_to': latest_image_file, 'archive': archive_path})

    def serve_file(self, filename):
        target = os.path.join(ROOT, filename)
        if not os.path.exists(target):
            self.send_error(404, 'File not found')
            return

        with open(target, 'rb') as handle:
            content = handle.read()

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content)

    def serve_image(self):
        if not os.path.exists(latest_image_file):
            self.send_error(404, 'No capture available yet')
            return

        with open(latest_image_file, 'rb') as handle:
            content = handle.read()

        self.send_response(200)
        self.send_header('Content-Type', 'image/jpeg')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content)

    def serve_json(self):
        if not os.path.exists(latest_meta_file):
            self.send_json(404, {'error': 'No capture available yet'})
            return

        with open(latest_meta_file, 'r', encoding='utf-8') as handle:
            content = handle.read()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def send_json(self, status_code, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == '__main__':
    server = ReceiverHTTPServer(get_bind_address(), ReceiverHandler)
    print(f'Receiver server listening on http://{HOST}:{PORT}')
    server.serve_forever()
