#!/usr/bin/env python3
"""Run the math-coach app on the laptop, without the board: same page, same API, same logic.

    python3 app/math-coach/dev_server.py [--port 7100] [--llm http://127.0.0.1:8081]

python/main.py is imported as it is; only the parts that need the board change:
  - the web server: App Lab's web_ui brick -> this standard-library server
  - the LED matrix: drawn in this terminal (and returned by /api/led)
  - the student data: python/data/profiles-dev.db, never the class's profiles.db
  - the model: any llama-server, e.g. the laptop's (start-llm.ps1 -Gpu)
Use a Python with numpy (e.g. ~/venv-ocr/bin/python) for the semantic families; without it
they fall back to the keyword topics.
"""
import argparse
import inspect
import json
import mimetypes
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")


def convert(fn, query):
    """Query string -> keyword arguments, typed by the function's annotations (as FastAPI does)."""
    kwargs = {}
    for name, param in inspect.signature(fn).parameters.items():
        if name in query:
            value = query[name]
            kwargs[name] = int(value) if param.annotation is int else value
        elif param.default is inspect.Parameter.empty:
            raise ValueError(f"missing parameter: {name}")
    return kwargs


def make_handler(routes):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if "/api/leaderboard" not in self.path and "/api/hint_status" not in self.path:
                sys.stderr.write("  " + fmt % args + "\n")

        def send(self, code, body, kind="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            if url.path in routes:
                query = dict(urllib.parse.parse_qsl(url.query))
                try:
                    return self.send(200, routes[url.path](**convert(routes[url.path], query)))
                except (ValueError, KeyError) as error:
                    return self.send(422, {"detail": str(error)})
            name = "index.html" if url.path in ("", "/") else url.path.lstrip("/")
            file = os.path.normpath(os.path.join(ASSETS, name))
            if file.startswith(ASSETS) and os.path.isfile(file):
                with open(file, "rb") as f:
                    return self.send(200, f.read(), mimetypes.guess_type(file)[0] or "application/octet-stream")
            return self.send(404, {"detail": "Not Found"})

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7100)
    ap.add_argument("--llm", default="http://127.0.0.1:8081", help="llama-server for rung 3")
    ap.add_argument("--db", default=os.path.join(HERE, "python", "data", "profiles-dev.db"))
    ap.add_argument("--quiet-led", action="store_true", help="don't draw the LED matrix in the terminal")
    args = ap.parse_args()
    os.environ["COACH_DB"] = args.db
    os.environ["COACH_LLM"] = args.llm
    os.environ["COACH_LED_PRINT"] = "0" if args.quiet_led else "1"
    sys.path.insert(0, os.path.join(HERE, "python"))
    import main as app  # noqa: E402  (python/main.py: sets everything up, without App Lab)
    print(f"Development server: http://{args.host}:{args.port}  (data: {args.db})", flush=True)
    ThreadingHTTPServer((args.host, args.port), make_handler(app.ROUTES)).serve_forever()


if __name__ == "__main__":
    main()
