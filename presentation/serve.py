"""Zero-dependency deck server.

Flask is not installed in every DSW snapshot, and a deck that cannot be
opened five minutes before a meeting is worthless. This serves the same
files with nothing but the standard library.

    python serve.py [--port 5051]

app.py is the Flask equivalent and serves the identical files wherever
Flask happens to be available. Both work because index.html uses
RELATIVE asset paths (static/css/...) rather than url_for().

Never open index.html over file:// — that blocks fetch() and any XHR
the deck makes, and you silently get the fallback state instead.
"""

import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))


class DeckHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean in ("/", "/index.html"):
            return os.path.join(ROOT, "templates", "index.html")
        return super().translate_path(path)

    def end_headers(self):
        # you WILL be editing slides while the browser is open
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "404" in (fmt % args):
            super().log_message(fmt, *args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5051)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    os.chdir(ROOT)
    srv = ThreadingHTTPServer((args.host, args.port), DeckHandler)
    print("deck on http://localhost:%d  (ctrl-c to stop)" % args.port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
