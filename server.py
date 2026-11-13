#!/usr/bin/env python3
"""Local web UI for generating images through the Codex backend.

  python3 server.py [--project DIR] [--port 8765]

Images are saved to <project>/images/renders/. The server binds to 127.0.0.1
only, because it uses your ChatGPT login token.
"""
import argparse
import json
import mimetypes
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import codex_client as cc

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY = 80 * 1024 * 1024  # uploads arrive as base64 data URLs
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class Handler(BaseHTTPRequestHandler):
    out_dir: Path = None
    project: Path = None

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[studio] {fmt % args}\n")

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path):
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), ctype)

    def _render_path(self, name):
        """Resolve a render file name safely inside out_dir, or None."""
        name = Path(name).name
        path = self.out_dir / name
        return path if path.suffix.lower() in IMAGE_EXTS and path.is_file() else None

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            return self._send_file(STATIC_DIR / "index.html")
        if route == "/api/config":
            return self._send(200, {
                "models": cc.list_models(),
                "default_model": cc.DEFAULT_MODEL,
                "project": str(self.project),
                "out_dir": str(self.out_dir),
            })
        if route == "/api/usage":
            try:
                return self._send(200, cc.get_usage())
            except cc.CodexError as e:
                return self._send(502, {"error": str(e)})
        if route.startswith("/renders/"):
            path = self._render_path(route[len("/renders/"):])
            return self._send_file(path) if path else self._send(404, {"error": "not found"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/generate":
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            return self._send(413, {"error": "Request too large (max 80 MB of images)."})
        try:
            req = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._send(400, {"error": "Invalid JSON"})

        prompt = (req.get("prompt") or "").strip()
        uploads = [u for u in req.get("images", []) if isinstance(u, str) and u.startswith("data:image/")]
        if not prompt and not uploads:
            return self._send(400, {"error": "Empty message"})

        # Earlier turns as text, so the model keeps the conversation context.
        items = []
        for m in req.get("history", []):
            text = (m.get("text") or "").strip()
            if text:
                items.append(cc.assistant_message(text) if m.get("role") == "assistant" else cc.user_message(text))
        # The latest generated images go along with the new message so follow-up edits work.
        previous = [p for p in (self._render_path(n) for n in req.get("previous_renders", [])) if p]
        note = "\n\n(Attached after any uploads: the most recent image(s) you generated.)" if previous else ""
        items.append(cc.user_message(prompt + note, uploads + [cc.file_to_data_url(p) for p in previous]))

        fmt = req.get("format") if req.get("format") in ("png", "jpeg", "webp") else "png"
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def emit(obj):
            self.wfile.write((json.dumps(obj) + "\n").encode())
            self.wfile.flush()

        try:
            for ev in cc.stream(items, model=req.get("model") or cc.DEFAULT_MODEL, size=req.get("size"),
                                quality=req.get("quality"), fmt=fmt, partial_images=2):
                if ev["type"] == "image":
                    path = cc.save_image(ev["b64"], self.out_dir, prompt or "edit", fmt)
                    print(f"[studio] saved {path}", file=sys.stderr)
                    emit({"type": "image", "name": path.name, "url": f"/renders/{path.name}",
                          "path": str(path), "revised_prompt": ev["revised_prompt"]})
                elif ev["type"] == "partial":
                    emit({"type": "partial", "data_url": f"data:image/{fmt};base64,{ev['b64']}"})
                else:
                    emit(ev)
            emit({"type": "done"})
        except cc.CodexError as e:
            emit({"type": "error", "message": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            print("[studio] client disconnected", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Local Codex image generation studio")
    ap.add_argument("-p", "--project", default=".", help="Project directory (default: current directory)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    Handler.project = Path(args.project).expanduser().resolve()
    Handler.out_dir = Handler.project / "images" / "renders"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Codex Image Studio: {url}\nSaving renders to {Handler.out_dir}", file=sys.stderr)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
