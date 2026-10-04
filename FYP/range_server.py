"""
HTTP file server that supports byte-range requests and counts the bytes it serves.

Used to measure how much of each COPC file is actually read when querying over HTTP.

Usage:
    python range_server.py data/copc_files --port 8000

Extra endpoints (not files):
    GET /__stats   -> {"bytes_served": ..., "requests": ...}
    GET /__reset   -> resets the counters to zero
"""
import argparse
import json
import os
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")

_lock = threading.Lock()
_stats = {"bytes_served": 0, "requests": 0}


def _count(n_bytes):
    with _lock:
        _stats["bytes_served"] += n_bytes
        _stats["requests"] += 1


class RangeHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the console quiet; stats are available at /__stats

    def _send_json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _resolve(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            self.send_error(404, "File not found")
            return None, None
        return path, os.path.getsize(path)

    def _parse_range(self, size):
        """Return (start, end) inclusive, or None for a full-file request."""
        header = self.headers.get("Range")
        if not header:
            return None
        m = RANGE_RE.match(header.strip())
        if not m:
            return "invalid"
        start_s, end_s = m.groups()
        if start_s == "" and end_s == "":
            return "invalid"
        if start_s == "":  # suffix range: last N bytes
            length = int(end_s)
            start, end = max(0, size - length), size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
            end = min(end, size - 1)
        if start > end or start >= size:
            return "invalid"
        return start, end

    def _send_headers(self, size, rng):
        if rng is None:
            self.send_response(200)
            self.send_header("Content-Length", str(size))
        else:
            start, end = rng
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()

    def do_HEAD(self):
        path, size = self._resolve()
        if path is None:
            return
        rng = self._parse_range(size)
        if rng == "invalid":
            self.send_error(416, "Invalid range")
            return
        self._send_headers(size, rng)  # HEAD sends no body, so nothing is counted

    def do_GET(self):
        if self.path == "/__stats":
            with _lock:
                return self._send_json(dict(_stats))
        if self.path == "/__reset":
            with _lock:
                _stats["bytes_served"] = 0
                _stats["requests"] = 0
            return self._send_json({"reset": True})

        path, size = self._resolve()
        if path is None:
            return
        rng = self._parse_range(size)
        if rng == "invalid":
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return

        self._send_headers(size, rng)
        start, end = (0, size - 1) if rng is None else rng
        length = end - start + 1

        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

        _count(length)


def main():
    parser = argparse.ArgumentParser(description="Byte-countingrange-request file server")
    parser.add_argument("directory", help="Folder to serve, e.g. data/copc_files")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    handler = partial(RangeHandler, directory=os.path.abspath(args.directory))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Serving {os.path.abspath(args.directory)} at http://127.0.0.1:{args.port}")
    print("Stats: /__stats   Reset: /__reset   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
