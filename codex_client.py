"""Minimal client for the Codex backend Responses endpoint with the image_generation tool.

Uses the ChatGPT login stored by Codex (~/.codex/auth.json) and always sends
store=false, so no conversation is created on the server.
"""
import base64
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_MODEL = "gpt-5.6-sol"
ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"
USAGE_ENDPOINT = "https://chatgpt.com/backend-api/wham/usage"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
AUTH_FILE = CODEX_HOME / "auth.json"
MODELS_CACHE = CODEX_HOME / "models_cache.json"
INSTRUCTIONS = (
    "You are an image generation assistant. When the user asks for an image or "
    "an edit, call the image_generation tool. Treat attached images as references "
    "or as the image to edit. Do not ask clarifying questions; make sensible "
    "choices. After generating, reply with one short sentence in the user's language."
)


class CodexError(Exception):
    pass


def load_auth():
    try:
        tokens = json.loads(AUTH_FILE.read_text())["tokens"]
        return tokens["access_token"], tokens["account_id"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as e:
        raise CodexError(f"Cannot read ChatGPT login from {AUTH_FILE}: {e}. Run `codex login` first.")


def list_models():
    """Model slugs Codex shows in its picker, from its local cache."""
    try:
        models = json.loads(MODELS_CACHE.read_text())["models"]
        slugs = [m["slug"] for m in sorted(models, key=lambda m: m.get("priority", 99))
                 if m.get("visibility") == "list"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        slugs = []
    if DEFAULT_MODEL not in slugs:
        slugs.insert(0, DEFAULT_MODEL)
    return slugs


def user_message(text, image_urls=()):
    content = [{"type": "input_text", "text": text}] if text else []
    content += [{"type": "input_image", "image_url": url} for url in image_urls]
    return {"type": "message", "role": "user", "content": content}


def assistant_message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def file_to_data_url(path):
    ext = Path(path).suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg"}.get(ext, ext)
    return f"data:image/{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"


def _sse_payloads(resp):
    data_lines = []
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line and data_lines:
            payload = "\n".join(data_lines)
            data_lines = []
            if payload != "[DONE]":
                yield json.loads(payload)


def stream(input_items, model=DEFAULT_MODEL, size=None, quality=None, fmt="png",
           partial_images=0, timeout=300):
    """Yield simplified events:
    {"type": "text", "delta"}, {"type": "partial", "b64"},
    {"type": "image", "b64", "revised_prompt"}, {"type": "status", "text"}.
    Raises CodexError on HTTP or server errors."""
    access_token, account_id = load_auth()
    tool = {"type": "image_generation", "output_format": fmt}
    if size and size != "auto":
        tool["size"] = size
    if quality and quality != "auto":
        tool["quality"] = quality
    if partial_images:
        tool["partial_images"] = partial_images
    body = {
        "model": model,
        "instructions": INSTRUCTIONS,
        "input": list(input_items),
        "tools": [tool],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "store": False,
        "stream": True,
    }
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {access_token}",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
        "originator": "codex_cli_rs",
        "session_id": str(uuid.uuid4()),
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for ev in _sse_payloads(resp):
                kind = ev.get("type", "")
                if kind == "response.output_text.delta":
                    yield {"type": "text", "delta": ev.get("delta", "")}
                elif kind == "response.image_generation_call.in_progress":
                    yield {"type": "status", "text": "generating"}
                elif kind == "response.image_generation_call.partial_image":
                    yield {"type": "partial", "b64": ev.get("partial_image_b64", "")}
                elif kind == "response.output_item.done":
                    item = ev.get("item", {})
                    if item.get("type") == "image_generation_call" and item.get("result"):
                        yield {"type": "image", "b64": item["result"],
                               "revised_prompt": item.get("revised_prompt", "")}
                elif kind in ("response.failed", "error"):
                    err = ev.get("response", {}).get("error") or ev.get("error") or ev
                    raise CodexError(f"Server error: {json.dumps(err)}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        hint = " Login may be expired: run `codex` once to refresh it." if e.code == 401 else ""
        raise CodexError(f"HTTP {e.code}: {detail}{hint}")
    except urllib.error.URLError as e:
        raise CodexError(f"Network error: {e.reason}")


def get_usage(timeout=30):
    """Plan and rate-limit windows for the logged-in ChatGPT account (no personal fields)."""
    access_token, account_id = load_auth()
    req = urllib.request.Request(USAGE_ENDPOINT, headers={
        "Authorization": f"Bearer {access_token}",
        "chatgpt-account-id": account_id,
        "originator": "codex_cli_rs",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        hint = " Login may be expired: run `codex` once to refresh it." if e.code == 401 else ""
        raise CodexError(f"Usage HTTP {e.code}.{hint}")
    except urllib.error.URLError as e:
        raise CodexError(f"Network error: {e.reason}")

    def window(w):
        if not w:
            return None
        return {"used_percent": w.get("used_percent", 0),
                "window_seconds": w.get("limit_window_seconds"),
                "reset_at": w.get("reset_at")}

    rl = data.get("rate_limit") or {}
    credits = data.get("credits") or {}
    return {
        "plan_type": data.get("plan_type"),
        "limit_reached": bool(rl.get("limit_reached")),
        "primary": window(rl.get("primary_window")),
        "secondary": window(rl.get("secondary_window")),
        "credits_balance": credits.get("balance"),
        "credits_unlimited": bool(credits.get("unlimited")),
    }


def slugify(text, limit=40):
    """ASCII file-name slug; strips accents so Vietnamese prompts stay readable."""
    text = unicodedata.normalize("NFKD", text.lower().replace("đ", "d"))
    text = text.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:limit].rstrip("-") or "image"


def save_image(b64, out_dir, name_hint, fmt="png"):
    """Write one image to out_dir with a timestamped, collision-free name; return its Path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if fmt == "jpeg" else fmt
    stem = f"{time.strftime('%Y%m%d-%H%M%S')}-{slugify(name_hint)}"
    path, n = out_dir / f"{stem}.{ext}", 1
    while path.exists():
        n += 1
        path = out_dir / f"{stem}-{n}.{ext}"
    path.write_bytes(base64.b64decode(b64))
    return path
