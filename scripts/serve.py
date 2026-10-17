"""Local dev server for web/: like `python3 -m http.server`, but every response says Cache-Control: no-store,
so a reload always shows the current code and data (browsers otherwise keep stale CSS/JS between edits).
Usage: python3 scripts/serve.py [port] [--bind ADDRESS]   (default 8642, 127.0.0.1; --bind 0.0.0.0 for a phone)."""
import argparse
import functools
import http.server
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


class NoStore(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class Server(http.server.ThreadingHTTPServer):
    # The page asks for about 15 modules at once. With socketserver's default listen backlog of 5, macOS resets the
    # connections beyond it ("Connection reset by peer"), and the page can hang at "Building the city 0%".
    request_queue_size = 128


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("port", nargs="?", type=int, default=8642)
    ap.add_argument("--bind", default="127.0.0.1")
    a = ap.parse_args(argv)
    handler = functools.partial(NoStore, directory=str(WEB))
    with Server((a.bind, a.port), handler) as httpd:
        print(f"serving {WEB} on http://{a.bind}:{a.port}/ (no-store)", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
