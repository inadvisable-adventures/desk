"""Parsing/rendering for a TODO.md-shaped file -- shared by the TODO
widget (widgets/todo/). See plans/todo-widget.md."""
import re
from dataclasses import dataclass
from pathlib import Path

TODO_FILENAME = "TODO.md"

# A top-level item start: a line beginning (no leading whitespace) with
# either a hash id (this project's own scheme, 7 lowercase hex digits) or
# a plain number (an older/other project's scheme), optionally preceded
# by a GitHub-style checklist marker ("- [ ] "/"- [x] ", another common
# other-project convention -- see TODO 5a2f5b9), followed by ". ".
# Generalized to match all of these since this reads arbitrary projects'
# TODO.md files, not just this one's. TODO 80de4d4: a plain markdown
# list bullet ("- id. ", "* id. ", "+ id. ", no checkbox) is accepted too --
# the natural way to write the id scheme in Markdown, which used to match
# nothing and so parsed as zero items. A bullet is kept in an item's
# raw_text (reordering never reformats) but is not part of its description.
ITEM_START_RE = re.compile(r"^(?:[-*+] (?:\[([ xX])\]\s+)?)?([0-9a-f]{7}|\d+)\.\s")

# Deliberately looser than ITEM_START_RE, used only to explain a file in
# which ITEM_START_RE recognized nothing: any line that, after optional
# indentation and a list marker ("-", "*", "+", "1.", "1)"), starts with a
# 7-hex id and ". " -- so "I see something item-shaped but can't read it"
# is told apart from a genuinely empty TODO list.
_ITEM_SHAPED_RE = re.compile(r"^\s*(?:(?:[-*+]|\d+[.)])\s+)?(?:\[[ xX]\]\s+)?[0-9a-f]{7}\.\s")

_WHITESPACE_RE = re.compile(r"\s+")

# The development-process.md plan marker: `[planned: some-file.md]`,
# appended to an item once it has a plan (see that file's Planning
# section). Captures the filename so a plan can be opened from the item.
_PLAN_RE = re.compile(r"\[planned:\s*([^\]]+?)\s*\]")


@dataclass
class TodoItem:
    item_id: str
    status: str  # "completed" | "superseded" | "pending" | "incomplete"
    description: str  # whitespace-collapsed, for display/truncation
    raw_text: str  # exact original text (including its own "id. " marker
    # line), preserved verbatim so reordering never reformats an item
    plan: str | None = None  # the [planned: <file>] filename, if any


def find_nearest_todo_file(start_dir: Path) -> Path | None:
    """Searches start_dir and its parents (in that order) for a
    TODO.md."""
    for directory in (start_dir, *start_dir.parents):
        candidate = directory / TODO_FILENAME
        if candidate.is_file():
            return candidate
    return None


def status_of(description: str) -> str:
    """Matches this project's own development-process.md conventions
    (COMPLETED:, SUPERSEDED by, PENDING) -- see plans/todo-widget.md's
    Scope section for why that's the right target, not universal
    TODO.md-format detection."""
    upper = description.lstrip().upper()
    if upper.startswith("SUPERSEDED"):
        return "superseded"
    if upper.startswith("COMPLETED"):
        return "completed"
    if upper.startswith("PENDING"):
        return "pending"
    return "incomplete"


def parse_todo_file(path: Path) -> tuple[str, list[TodoItem]]:
    """Returns (preamble_text, items). preamble_text is everything before
    the first item (title, intro prose)."""
    lines = path.read_text().splitlines(keepends=True)
    starts = [
        (m.group(2), m.group(1), i) for i, line in enumerate(lines) if (m := ITEM_START_RE.match(line))
    ]

    preamble = "".join(lines[: starts[0][2]]) if starts else "".join(lines)

    items = []
    for idx, (item_id, checkbox, start) in enumerate(starts):
        end = starts[idx + 1][2] if idx + 1 < len(starts) else len(lines)
        raw_text = "".join(lines[start:end])
        description = ITEM_START_RE.sub("", raw_text, count=1)
        collapsed = _WHITESPACE_RE.sub(" ", description).strip()
        status = status_of(collapsed)
        if status == "incomplete" and checkbox is not None and checkbox.lower() == "x":
            # No explicit COMPLETED:/SUPERSEDED/PENDING description
            # prefix (this project's own convention) -- fall back to a
            # checked GitHub-style checklist marker instead.
            status = "completed"
        plan_match = _PLAN_RE.search(raw_text)
        items.append(
            TodoItem(
                item_id=item_id,
                status=status,
                description=collapsed,
                raw_text=raw_text,
                plan=plan_match.group(1) if plan_match else None,
            )
        )
    return preamble, items


def unrecognized_items_message(path: Path) -> str | None:
    """TODO 80de4d4: when parse_todo_file finds no items in `path` but the file
    has item-shaped lines (an id followed by ". " behind indentation or an
    unsupported list marker), a message saying so -- otherwise None. An
    empty item list is otherwise indistinguishable from "nothing to do",
    which is how a mis-formatted TODO.md used to fail silently. Run
    `python3 scripts/todo_item_ids.py canonicalize TODO.md` to reformat."""
    lines = path.read_text().splitlines()
    if any(ITEM_START_RE.match(line) for line in lines):
        return None
    shaped = [i + 1 for i, line in enumerate(lines) if _ITEM_SHAPED_RE.match(line)]
    if not shaped:
        return None
    shown = ", ".join(str(n) for n in shaped[:5]) + (", ..." if len(shaped) > 5 else "")
    return (
        f"{path.name}: no items recognized, but {len(shaped)} line(s) look like item starts "
        f"(line {shown}) in a shape this parser does not read -- items must start at column 0 as "
        f"'<id>. ', '- <id>. ', or '- [ ] <id>. '. Reformat with "
        f"`python3 scripts/todo_item_ids.py canonicalize {path.name}`."
    )


def render_todo_file(preamble: str, items: list[TodoItem]) -> str:
    """Reassembles file text from a preamble plus items in their current
    list order -- reordering never touches an item's raw_text, only its
    position."""
    return preamble + "".join(item.raw_text for item in items)


def truncate_description(description: str, limit: int = 100) -> str:
    if len(description) <= limit:
        return description
    return description[:limit] + "..."
