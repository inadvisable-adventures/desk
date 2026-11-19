#!/usr/bin/env python3
"""Mints a tempui changelog tag and writes it as its own file in src/desk/tempui_content/ (TODO de16076).

    python3 scripts/new_tempui_changelog_entry.py "short summary, 10-50 chars" --description "What an agent now needs to know."
    python3 scripts/new_tempui_changelog_entry.py "short summary" [--breaking] < description.md

One new file per change, so concurrent branches never touch the same file. Prints the tag id (also use it in
TODO.md and tests). See the docstring of src/desk/tempui_content.py for the file format.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("summary", help="10-50 characters; becomes the tag's visible name")
    parser.add_argument("--description", help="the Markdown body; read from stdin if omitted")
    parser.add_argument("--breaking", action="store_true", help="a breaking change rather than a new feature")
    parser.add_argument("--dir", type=Path, default=REPO / "src" / "desk" / "tempui_content", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    from desk.temp_ui import generate_tag  # imported late: it loads (and checks) the existing content

    description = args.description if args.description is not None else sys.stdin.read()
    if not description.strip():
        parser.error("a description is required (--description or stdin)")
    try:
        tag = generate_tag(args.summary)
    except ValueError as e:
        parser.error(str(e))
    now = time.localtime()
    entry = {"tag": tag.id, "monthstamp": time.strftime("%m %Y", now), "description": description.strip("\n") + "\n"}
    if args.breaking:
        entry["breaking"] = True
    slug = re.sub(r"[^a-z0-9]+", "-", args.summary.lower()).strip("-")[:40] or "entry"
    path = args.dir / f"{time.strftime('%Y-%m-%d', now)}-{slug}-{tag.hash}.json"
    path.write_text(json.dumps([entry], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(tag.id)
    print(f"wrote {path.relative_to(REPO) if path.is_relative_to(REPO) else path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
