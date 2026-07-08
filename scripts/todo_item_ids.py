#!/usr/bin/env python3
"""Generate/convert stable TODO item ids.

Each TODO item gets a permanent 7-lowercase-hex-digit id, assigned once
and never recomputed afterward -- see development-process.md's "Item IDs"
section and how-to-convert-item-id-one-time.md for the full scheme and
the one-time conversion procedure this implements. Id generation itself
lives in desk.todo_ids (shared with the TODO widget, widgets/todo/).

Usage:
    python3 scripts/todo_item_ids.py new "<item description text>"
        Prints a fresh id for a brand-new TODO item.

    python3 scripts/todo_item_ids.py convert TODO.md
        One-time bulk conversion: rewrites every top-level numbered item
        ("N. description...") to use a hash id instead of its number, and
        rewrites every "item N" cross-reference elsewhere in the file to
        "TODO <id>". Prints the number -> id mapping it used.
"""
import re
import sys
from pathlib import Path

from desk.todo_ids import make_item_id

# A top-level item start: a line beginning (no leading whitespace) with
# digits, a period, and a space -- e.g. "12. Fix the thing". Only plain
# numbers: this script converts *from* that format, so a match here is
# never expected to already be a hash id.
ITEM_START_RE = re.compile(r"^(\d+)\.\s")


def _split_items(lines: list[str]) -> list[tuple[int, int, int]]:
    """Returns (number, start_index, end_index) for each top-level
    numbered item (end_index is exclusive)."""
    starts = [
        (int(m.group(1)), i)
        for i, line in enumerate(lines)
        if (m := ITEM_START_RE.match(line))
    ]
    items = []
    for idx, (number, start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
        items.append((number, start, end))
    return items


def convert(path: Path) -> dict[int, str]:
    lines = path.read_text().splitlines(keepends=True)
    items = _split_items(lines)

    number_to_id = {}
    for number, start, end in items:
        body = "".join(lines[start:end])
        description = ITEM_START_RE.sub("", body, count=1)
        number_to_id[number] = make_item_id(description)

    for number, start, _end in items:
        lines[start] = ITEM_START_RE.sub(f"{number_to_id[number]}. ", lines[start], count=1)

    text = "".join(lines)

    # Plural, slash-separated references first ("items 16/17/21/23") --
    # must run before the singular pass below, or "items 16/17" would be
    # left with its leading "items" word dangling once "17" alone got
    # replaced by the singular pass.
    def _replace_plural(m: re.Match) -> str:
        numbers = m.group(1).split("/")
        return "/".join(f"TODO {number_to_id[int(n)]}" for n in numbers)

    text = re.sub(r"\bitems\s+(\d+(?:/\d+)+)\b", _replace_plural, text)

    for number, item_id in number_to_id.items():
        # \s+ (not a literal " "): a reference can be word-wrapped across
        # lines, e.g. "...done when item\n    10 was built" -- confirmed
        # directly in this project's own TODO.md.
        text = re.sub(rf"\bitem\s+{number}\b", f"TODO {item_id}", text)

    path.write_text(text)
    return number_to_id


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "new":
        print(make_item_id(" ".join(argv[1:])))
        return 0
    if len(argv) == 2 and argv[0] == "convert":
        mapping = convert(Path(argv[1]))
        for number in sorted(mapping):
            print(f"{number} -> {mapping[number]}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
