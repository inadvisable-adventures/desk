#!/usr/bin/env python3
"""Generate/convert stable TODO item ids.

Each TODO item gets a permanent 7-lowercase-hex-digit id, assigned once
and never recomputed afterward -- see development-process.md's "Item IDs"
section and how-to-convert-item-id-one-time.md for the full scheme and
the one-time conversion procedure this implements.

This file is meant to be copied verbatim into other projects (seeded
alongside development-process.md on "New Desk" creation -- TODO
c458012), so it's deliberately self-contained: no import of this app's
own `desk` package, which a destination project won't have installed.

Usage:
    python3 scripts/todo_item_ids.py new "<item description text>"
        Prints a fresh id for a brand-new TODO item.

    python3 scripts/todo_item_ids.py convert TODO.md
        One-time bulk conversion: rewrites every top-level numbered item
        ("N. description...") to use a hash id instead of its number, and
        rewrites every "item N" cross-reference elsewhere in the file to
        "TODO <id>". Prints the number -> id mapping it used.
"""
import hashlib
import re
import secrets
import sys
from pathlib import Path

ID_LENGTH = 7
SHORT_DESCRIPTION_THRESHOLD = 10


def make_item_id(description: str) -> str:
    """Stable id derived from an item's description at the moment the id
    is assigned. If the description is shorter than
    SHORT_DESCRIPTION_THRESHOLD characters, hash a random string instead
    (a short description alone wouldn't give a well-distributed hash).
    Once assigned, this is just an opaque label -- never recompute it from
    a later-edited description.

    Kept as an independent copy of desk.todo_ids.make_item_id (used
    directly by widgets/todo/widget.py, which always runs with the
    `desk` package available) rather than imported from it -- see this
    file's own module docstring for why."""
    text = description if len(description) >= SHORT_DESCRIPTION_THRESHOLD else secrets.token_hex(8)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:ID_LENGTH]


# A top-level item start: a line beginning (no leading whitespace) with
# digits, a period, and a space -- e.g. "12. Fix the thing". Only plain
# numbers: this script converts *from* that format, so a match here is
# never expected to already be a hash id.
ITEM_START_RE = re.compile(r"^(\d+)\.\s")


def _html_comment_line_indices(lines: list[str]) -> set[int]:
    """Line indices lying inside a (possibly multi-line) `<!-- ... -->`
    block. ITEM_START_RE has no HTML-comment awareness at all, so a
    documentation comment containing its own literal example lines
    (e.g. a `<!-- Item format: 1. ... 2. ... -->`-shaped block whose
    `1.`/`2.` lines are written across multiple physical lines) would
    otherwise be treated as real item boundaries. Deliberately
    line-based, not a full HTML parse -- this script only ever runs
    against its own project's self-authored TODO.md, not arbitrary
    external HTML. A comment opened and closed on the same line needs
    no masking at all (nothing else on that line can be a
    ITEM_START_RE match at column 0 once "<!--" has already appeared)."""
    inside = set()
    in_comment = False
    for i, line in enumerate(lines):
        if in_comment:
            inside.add(i)
            if "-->" in line:
                in_comment = False
            continue
        start = line.find("<!--")
        if start != -1 and "-->" not in line[start:]:
            in_comment = True
    return inside


def _split_items(lines: list[str]) -> list[tuple[int, int, int]]:
    """Returns (number, start_index, end_index) for each top-level
    numbered item (end_index is exclusive)."""
    comment_lines = _html_comment_line_indices(lines)
    starts = [
        (int(m.group(1)), i)
        for i, line in enumerate(lines)
        if i not in comment_lines and (m := ITEM_START_RE.match(line))
    ]
    items = []
    for idx, (number, start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
        items.append((number, start, end))
    return items


def _mask_for_text(text: str) -> list[bool]:
    """A per-character mask (True = falls inside an HTML comment line)
    aligned to `text` -- used so the cross-reference passes below can
    reject a match that touches a comment line, the same way
    _split_items already does for item boundaries. Needed because those
    passes deliberately allow \\s+ to span multiple lines (a legitimate
    word-wrapped reference), which can otherwise reach across a comment
    boundary into the comment's own literal prose/example text and
    corrupt it -- confirmed directly with a fixture where the phrase
    "...not a real item" immediately precedes a comment-embedded
    "2. ..." example line: the singular pass's cross-line \\s+ matched
    "item\\n2" there, silently merging two lines.

    Recomputed fresh from `text` before *each* substitution pass below,
    not reused across passes -- a pass can change `text`'s length (a
    word-wrapped match collapsing onto one line), which would otherwise
    desync a mask computed against an earlier version of `text`. Safe
    to recompute: comment markers themselves are never inside a match
    this function would allow through (any match touching a comment
    line is skipped unchanged), so the comment spans this detects stay
    correct across every pass."""
    lines = text.splitlines(keepends=True)
    comment_lines = _html_comment_line_indices(lines)
    mask = []
    for i, line in enumerate(lines):
        mask.extend([i in comment_lines] * len(line))
    return mask


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

    def _skip_if_masked(m: re.Match, mask: list[bool], replace) -> str:
        if any(mask[m.start():m.end()]):
            return m.group(0)
        return replace(m)

    # Plural, slash-separated references first ("items 16/17/21/23") --
    # must run before the singular pass below, or "items 16/17" would be
    # left with its leading "items" word dangling once "17" alone got
    # replaced by the singular pass.
    def _replace_plural(m: re.Match) -> str:
        numbers = m.group(1).split("/")
        return "/".join(f"TODO {number_to_id[int(n)]}" for n in numbers)

    mask = _mask_for_text(text)
    text = re.sub(r"\bitems\s+(\d+(?:/\d+)+)\b", lambda m: _skip_if_masked(m, mask, _replace_plural), text)

    # Plural, en-dash/hyphen ranges ("items 6-8", "items 6–8") -- also
    # must run before the singular pass below, same reasoning as the
    # slash-separated case above. Expands to every number in the
    # inclusive range, slash-joined the same way the slash-list case
    # renders, so downstream text reads consistently either way.
    def _replace_range(m: re.Match) -> str:
        start, end = int(m.group(1)), int(m.group(2))
        return "/".join(f"TODO {number_to_id[n]}" for n in range(start, end + 1))

    mask = _mask_for_text(text)
    text = re.sub(r"\bitems\s+(\d+)\s*[-–]\s*(\d+)\b", lambda m: _skip_if_masked(m, mask, _replace_range), text)

    for number, item_id in number_to_id.items():
        # \s+ (not a literal " "): a reference can be word-wrapped across
        # lines, e.g. "...done when item\n    10 was built" -- confirmed
        # directly in this project's own TODO.md. The optional leading
        # "TODO\s+" (and matching it into the replacement) avoids
        # double-prefixing an already-prefixed reference like "TODO item
        # 16" into "TODO TODO <id>" -- both "TODO item 16" and "item 16"
        # become plain "TODO <id>".
        mask = _mask_for_text(text)
        text = re.sub(
            rf"\b(?:TODO\s+)?item\s+{number}\b",
            lambda m, item_id=item_id, mask=mask: _skip_if_masked(m, mask, lambda _m: f"TODO {item_id}"),
            text,
        )

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
