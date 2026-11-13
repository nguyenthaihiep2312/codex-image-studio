#!/usr/bin/env python3
"""Generate images by calling the Codex backend directly with the image_generation tool.

Uses the ChatGPT login stored by Codex (~/.codex/auth.json). Requests are sent
with store=false, so no conversation is created. Images are written to
<project>/images/renders/.

Usage:
  codex-image-gen.py "a red bicycle on a beach at sunset"
  codex-image-gen.py -p ~/my-project -i ref1.png -i ref2.jpg "combine these into one poster"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_client as cc  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Generate images via the Codex backend image_generation tool.")
    ap.add_argument("prompt", help="Image description")
    ap.add_argument("-m", "--model", default=cc.DEFAULT_MODEL, help=f"Model (default: {cc.DEFAULT_MODEL})")
    ap.add_argument("-p", "--project", default=".", help="Project directory (default: current directory)")
    ap.add_argument("-i", "--image", action="append", default=[], help="Reference image (repeatable)")
    ap.add_argument("-n", "--name", help="Output file name hint (default: the prompt)")
    ap.add_argument("--size", help="1024x1024, 1536x1024, 1024x1536 or auto (the server may ignore it)")
    ap.add_argument("--quality", choices=["low", "medium", "high", "auto"])
    ap.add_argument("--format", default="png", choices=["png", "jpeg", "webp"])
    ap.add_argument("--timeout", type=int, default=300, help="Seconds (default: 300)")
    args = ap.parse_args()

    out_dir = Path(args.project).expanduser().resolve() / "images" / "renders"
    refs = [cc.file_to_data_url(Path(p).expanduser()) for p in args.image]
    print(f"Generating with {args.model}...", file=sys.stderr)
    saved, text = [], []
    try:
        for ev in cc.stream([cc.user_message(args.prompt, refs)], model=args.model, size=args.size,
                            quality=args.quality, fmt=args.format, timeout=args.timeout):
            if ev["type"] == "image":
                path = cc.save_image(ev["b64"], out_dir, args.name or args.prompt, args.format)
                saved.append(path)
                print(path)
            elif ev["type"] == "text":
                text.append(ev["delta"])
    except cc.CodexError as e:
        sys.exit(str(e))
    if not saved:
        said = "".join(text).strip()
        sys.exit(f"No image returned.{' Model said: ' + said if said else ''}")


if __name__ == "__main__":
    main()
