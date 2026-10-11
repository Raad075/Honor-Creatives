#!/usr/bin/env python3
"""
Local server for the Adcelerete battery ad.

  python serve.py            -> http://localhost:8000      (test on this computer)
  python serve.py --https    -> https://<your-LAN-IP>:8000 (test on your real phone)
  python serve.py --port 9000

Why --https? The Battery API only works in a "secure context" (https or localhost).
To test on a phone over Wi-Fi you need https. --https makes a self-signed
certificate (needs `openssl` installed); accept the browser warning on the phone.
"""
import argparse
import http.server
import os
import re
import socket
import socketserver
import ssl
import subprocess
import threading
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


class Handler(http.server.SimpleHTTPRequestHandler):
    """Static handler with HTTP Range support (needed for reliable <video> seeking)."""

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if rng and os.path.isfile(path):
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                size = os.path.getsize(path)
                start = int(m.group(1)) if m.group(1) else 0
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                if start > end:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    return
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", self.guess_type(path))
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.end_headers()
                try:
                    with open(path, "rb") as f:
                        f.seek(start)
                        self.wfile.write(f.read(length))
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
        try:
            super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt, *args):
        pass  # keep the console quiet


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def make_cert():
    cert, key = os.path.join(ROOT, ".cert.pem"), os.path.join(ROOT, ".key.pem")
    if not (os.path.exists(cert) and os.path.exists(key)):
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", key, "-out", cert, "-days", "30", "-subj", "/CN=localhost"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    return cert, key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--https", action="store_true", help="serve over https (for phone testing)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    host = "0.0.0.0" if args.https else "127.0.0.1"
    httpd = Server((host, args.port), Handler)
    scheme = "http"
    if args.https:
        cert, key = make_cert()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    local = f"{scheme}://localhost:{args.port}/index.html"
    print(f"\n  Ad running:  {local}")
    if args.https:
        print(f"  On your phone (same Wi-Fi): {scheme}://{lan_ip()}:{args.port}/index.html")
        print("  (accept the certificate warning once)")
    print("  Ctrl+C to stop\n")

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(local)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
