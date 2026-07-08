import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

TEMP_UI_DIRNAME = ".desk_temp"
DOC_FILENAME = "desk-temporary-ui.md"
GITIGNORE_ENTRY = ".desk_temp/"

DOC_TEMPLATE = """# Temporary UI

This directory holds "temporary UI" files: a lightweight way for an
agent (or any external process) to ask a question through Desk's own
canvas instead of a terminal prompt.

Each file is named with a bare UUID (e.g.
`550e8400-e29b-41d4-a716-446655440000`, no extension). Desk watches
this directory: a newly-created file shows up as a clickable
notification in the app's upper-right corner; clicking it places a new
widget on the canvas, centered in the current view. There are two file
types, distinguished by their first line's keyword — `Question` (below)
or `LightningRound` (further down).

## The TempUI DSL: Question

Each line is `keyword rest-of-line...` — everything after the first
space is a single natural-language value (a question, an option label,
an answer), not further split into separate parameters.

Supported keywords (more may be added later; unrecognized keywords are
ignored, not an error):

- `Question <text>` — the question shown to the user.
- `Option <text>` — one selectable choice. Repeat for each option.
- `Answer <text>` — appended automatically once the user picks an
  option; do not write this yourself.

Example, before an answer is given:

```
Question What color should the header be?
Option Red
Option Green
Option Blue
```

After the user clicks "Green":

```
Question What color should the header be?
Option Red
Option Green
Option Blue
Answer Green
```

## The TempUI DSL: LightningRound

For asking the *same* multiple-choice question repeatedly over a list of
items (e.g. classifying a batch of words, reviewing a batch of files),
one at a time, answerable by clicking a button or pressing a single
keyboard key — instead of writing one `Question` file per item.

Lines with more than one value are **tab**-separated (not
space-separated like `Question`/`Option`/`Answer` above), since a name,
prompt, or description may itself contain spaces:

- `LightningRound<TAB>name<TAB>prompt` — **must be the first line**.
  `name` is a short label; `prompt` is the question asked about every
  item (e.g. "Is this word a noun, verb, or adjective?").
- `Option <character>` — reused from the `Question` type verbatim
  (space-separated, not tab-separated). The value is a single character,
  used both as the option's keyboard shortcut and its on-screen label.
  Repeat once per option — at least two. These options apply to every
  item in the file, not just one.
- `LRItem<TAB>description<TAB>answer` — one "lightning round item".
  `answer` is the literal string `unanswered` until the user picks an
  option, at which point Desk replaces it with that option's character
  — do not write anything other than `unanswered` here yourself. Repeat
  for each item; Desk shows one unanswered item at a time (in file
  order), skipping any that already have a real answer.

Example, before any answers:

```
LightningRound	Vocab Drill	Is this word a noun, verb, or adjective?
Option N
Option V
Option A
LRItem	run	unanswered
LRItem	quick	unanswered
```

After the user answers "run" with "V" (pressing the `V` key or clicking
its button):

```
LightningRound	Vocab Drill	Is this word a noun, verb, or adjective?
Option N
Option V
Option A
LRItem	run	V
LRItem	quick	unanswered
```

This file (`desk-temporary-ui.md`) is itself ignored by the file
watcher — its name isn't a UUID, so it's never mistaken for a temp UI
file.
"""


@dataclass
class TempUiDocument:
    question: str | None = None
    options: list[str] = field(default_factory=list)
    answer: str | None = None


LIGHTNING_ROUND_KEYWORD = "LightningRound"
UNANSWERED = "unanswered"


@dataclass
class LightningRoundItem:
    description: str
    answer: str | None = None  # None means "unanswered"


@dataclass
class LightningRoundDocument:
    name: str = ""
    prompt: str = ""
    options: list[str] = field(default_factory=list)
    items: list[LightningRoundItem] = field(default_factory=list)


def detect_temp_ui_kind(text: str) -> str:
    """"question" (the original, default type) or "lightning_round",
    read from the first non-blank line's keyword -- lets a caller that's
    seeing a temp-ui file for the first time (a notification, a saved
    Desk's widget state) know which widget kind to place without
    assuming "question"."""
    for line in text.splitlines():
        if line.strip():
            keyword = line.split(None, 1)[0]
            return "lightning_round" if keyword == LIGHTNING_ROUND_KEYWORD else "question"
    return "question"


def is_temp_ui_filename(name: str) -> bool:
    try:
        uuid.UUID(name)
        return True
    except ValueError:
        return False


def parse_temp_ui(text: str) -> TempUiDocument:
    doc = TempUiDocument()
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        keyword = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ""
        if keyword == "Question":
            doc.question = rest
        elif keyword == "Option":
            doc.options.append(rest)
        elif keyword == "Answer":
            doc.answer = rest
        # Unrecognized keywords are ignored -- forward-compatible with
        # future DSL additions, not an error.
    return doc


def append_answer(path: Path, answer: str) -> str:
    """Appends an Answer line and returns the full resulting file text,
    so a caller can record it for self-write suppression (see
    desk.shell.temp_ui_manager.TempUiManager) without a second read."""
    with path.open("a") as f:
        f.write(f"Answer {answer}\n")
    return path.read_text()


def parse_lightning_round(text: str) -> LightningRoundDocument:
    doc = LightningRoundDocument()
    for line in text.splitlines():
        if not line.strip():
            continue
        if line == LIGHTNING_ROUND_KEYWORD or line.startswith(LIGHTNING_ROUND_KEYWORD + "\t"):
            parts = line.split("\t")
            doc.name = parts[1] if len(parts) > 1 else ""
            doc.prompt = parts[2] if len(parts) > 2 else ""
        elif line.startswith("Option"):
            # Reused verbatim from the Question DSL -- space-separated,
            # not tab-separated, since its value is a single character
            # with no internal spaces to disambiguate.
            parts = line.split(None, 1)
            if len(parts) > 1:
                doc.options.append(parts[1].strip())
        elif line.startswith("LRItem"):
            parts = line.split("\t")
            description = parts[1] if len(parts) > 1 else ""
            raw_answer = parts[2] if len(parts) > 2 else UNANSWERED
            doc.items.append(
                LightningRoundItem(description, None if raw_answer == UNANSWERED else raw_answer)
            )
        # Unrecognized keywords are ignored, same as parse_temp_ui.
    return doc


def record_lightning_round_answer(path: Path, item_index: int, character: str) -> str:
    """Rewrites the item_index-th LRItem line's answer field in place
    (item_index counts only LRItem lines, in file order -- matching
    parse_lightning_round's doc.items indexing) and returns the full
    resulting file text, same self-write-suppression shape as
    append_answer. Every other line, including other LRItem lines, is
    left byte-for-byte untouched."""
    lines = path.read_text().splitlines(keepends=True)
    seen = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if not stripped.startswith("LRItem"):
            continue
        if seen == item_index:
            parts = stripped.split("\t")
            description = parts[1] if len(parts) > 1 else ""
            newline = "\n" if line.endswith("\n") else ""
            lines[i] = f"LRItem\t{description}\t{character}{newline}"
            break
        seen += 1
    text = "".join(lines)
    path.write_text(text)
    return text


def ensure_gitignore_entry(git_root: Path, ask: Callable[[], bool]) -> None:
    gitignore_path = git_root / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    if any(line.strip().rstrip("/") == ".desk_temp" for line in existing.splitlines()):
        return
    if not ask():
        return
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    gitignore_path.write_text(prefix + GITIGNORE_ENTRY + "\n")
