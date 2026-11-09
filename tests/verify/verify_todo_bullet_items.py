"""TODO 80de4d4: TODO.md items written as markdown list bullets
("- 4f9f415. ...") used to parse as zero items, silently. Covers the widened
ITEM_START_RE, verbatim round-trip (bullet kept in raw_text, stripped from the
description), the loud "item-shaped but unreadable" message the MCP tools and
widget use, and `scripts/todo_item_ids.py canonicalize`."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from desk.todo_file import parse_todo_file, render_todo_file, unrecognized_items_message  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


BULLETED = """# TODO

Intro.

- 4f9f415. COMPLETED: Build a pipeline
  with a continuation line.

* a1b2c3d. Second item [planned: p.md]
+ b2c3d4e. Third
- [x] c3d4e5f. Checklist done
- [ ] d4e5f6a. Checklist open
e5f6a7b. Bare item
"""

with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "TODO.md"
    path.write_text(BULLETED)
    preamble, items = parse_todo_file(path)
    check("every bullet shape yields an item (6)", [i.item_id for i in items] == ["4f9f415", "a1b2c3d", "b2c3d4e", "c3d4e5f", "d4e5f6a", "e5f6a7b"])
    check("preamble stops before the first bullet", preamble == "# TODO\n\nIntro.\n\n")
    check("bullet is not part of the description", items[0].description == "COMPLETED: Build a pipeline with a continuation line.")
    check("status and plan still read", items[0].status == "completed" and items[1].plan == "p.md")
    check("checkbox state still read", items[3].status == "completed" and items[4].status == "incomplete")
    check("raw_text keeps the bullet; render round-trips byte-for-byte", render_todo_file(preamble, items) == BULLETED)
    check("a parsed file gives no unrecognized message", unrecognized_items_message(path) is None)

    # item-shaped but unreadable -> loud
    indented = Path(d) / "indented.md"
    indented.write_text("# T\n\n  - 4f9f415. indented item\n  - a1b2c3d. another\n")
    _, none = parse_todo_file(indented)
    msg = unrecognized_items_message(indented)
    check("indented items still parse as zero", none == [])
    check("...but the message names the count, lines and the fix",
          msg is not None and "2 line(s)" in msg and "line 3, 4" in msg and "canonicalize" in msg)
    plain = Path(d) / "plain.md"
    plain.write_text("# T\n\nJust prose, no items. Version 1.2.3 released.\n")
    check("a genuinely item-free file gives no message", unrecognized_items_message(plain) is None)
    empty = Path(d) / "empty.md"
    empty.write_text("")
    check("an empty file gives no message", unrecognized_items_message(empty) is None)

    # canonicalize
    script = ["python3", "scripts/todo_item_ids.py", "canonicalize"]
    messy = Path(d) / "messy.md"
    text = ("# T\n\n- 4f9f415. one\n  cont\n1. a1b2c3d. two\n2) b2c3d4e. three\n- [ ] c3d4e5f. kept\n"
            "d4e5f6a. bare\n  - e5f6a7b. indented\n```\n- f6a7b8c. in a fence\n```\n<!--\n- 0123456. in comment\n-->\n")
    messy.write_text(text)
    r = subprocess.run(script + [str(messy), "--dry-run"], capture_output=True, text=True)
    check("--dry-run reports and does not write", "would rewrite 3" in r.stdout and messy.read_text() == text)
    r = subprocess.run(script + [str(messy)], capture_output=True, text=True)
    out = messy.read_text()
    check("rewrites bullets and ordered markers", "\n4f9f415. one\n" in out and "\na1b2c3d. two\n" in out and "\nb2c3d4e. three\n" in out)
    check("leaves checklist, bare, fenced and commented lines alone",
          "- [ ] c3d4e5f. kept" in out and "\nd4e5f6a. bare\n" in out and "- f6a7b8c. in a fence" in out and "- 0123456. in comment" in out)
    check("lists the indented item for manual review, unchanged",
          "needs manual review: line 9" in r.stdout and "  - e5f6a7b. indented" in out)
    _, items = parse_todo_file(messy)
    # (the parser itself is not fence/comment aware, as before: only compare the real items)
    check("after canonicalize the readable items parse", [i.item_id for i in items][:5] == ["4f9f415", "a1b2c3d", "b2c3d4e", "c3d4e5f", "d4e5f6a"])
    r2 = subprocess.run(script + [str(messy)], capture_output=True, text=True)
    check("idempotent", "rewrote 0" in r2.stdout and messy.read_text() == out)

# this repo's own TODO.md is unaffected by the wider regex
_, own = parse_todo_file(Path("TODO.md"))
check("the project's own TODO.md still parses to the same shape (ids unique, non-empty)", len(own) > 0 and len({i.item_id for i in own}) == len(own))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
