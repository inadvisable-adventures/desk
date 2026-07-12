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
widget on the canvas, centered in the current view. There are five
file types, distinguished by their first line's keyword — `Question`
(below), `LightningRound` (further down), `OpenMarkdown` (further down
still), `Scratch` (further down still), or `Markdown` (further down
still).

## Questions for the user: use QUESTIONS.md, not this DSL

If you have an open-ended question *for the user* — something you're
genuinely blocked on and need their input to resolve, as opposed to a
single quick multiple-choice decision (`Question`/`LightningRound`
below are for that) — write it to `QUESTIONS.md` at the project root
instead of creating a file here. Each entry is a `## <short summary>`
heading, the question's own text below it, then a trailing
`(Answer: )` placeholder line for the user to fill in (leave it empty;
never write your own guess into it). If `QUESTIONS.md` doesn't exist
yet, create it with a `# Questions with optional answers` title line
first.

Desk watches `QUESTIONS.md` the same way it watches this directory: a
newly-added entry surfaces as a top-right notification, which either
focuses an already-open Questions widget or opens a new one, letting
the user answer directly from the canvas. This is on top of whatever
your own working conventions already say about tracking questions
(e.g. this project's own `development-process.md`, if it has one) —
follow those for *when* to ask, use `QUESTIONS.md` as *where* the
question itself lives.

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

## The TempUI DSL: OpenMarkdown

For telling Desk to open a Markdown file in the Markdown widget — a
fire-and-forget instruction, not a question: there is no `Answer`
line, and Desk never writes back to this file. This is a *pointer* to
an existing file elsewhere on disk — if you want to give Desk markdown
content directly instead, use `Markdown` below.

- `OpenMarkdown <path>` — the first (and normally only) line. `path`
  is the file to open, absolute or relative to the current Desk's
  directory. Like `Question <text>`, everything after the first space
  is one opaque value, so a path containing spaces needs no escaping.

Example:

```
OpenMarkdown ./diagrams.md
```

Clicking the notification opens `path` in a new Markdown widget
instance, centered in the current view.

## The TempUI DSL: Scratch

For giving Desk arbitrary free-form notes to show in a Scratch widget —
a fire-and-forget instruction, not a question: there is no `Answer`
line, and Desk never writes back to this file.

- The first line is `Scratch <label>` — `label` becomes the widget's
  title (`Scratch: <label>`).
- Every line after that, verbatim, becomes the widget's initial body
  text (not further parsed — write whatever you want here).

Example:

```
Scratch Investigation notes
Found the bug in file_watch.py line 42.
Still need to check the TempUiManager path.
```

If the user says "scratch" in conversation, this capability is almost
certainly what's meant — not some other, more generic sense of the
word — unless a clearly more pressing local meaning has already been
established earlier in the current conversation.

## The TempUI DSL: Markdown

For giving Desk markdown *content* directly, rendered in the Markdown
widget — unlike `OpenMarkdown` above, there is no separate target file:
this file's own content *is* the markdown. Fire-and-forget, same as
`OpenMarkdown`/`Scratch`: there is no `Answer` line, and Desk never
writes back to this file.

- The first line is `Markdown <label>` — `label` is used for the
  notification text; it is *not* used for anything saved to disk.
- Every line after that, verbatim, is the markdown to render (not
  further parsed here — write real markdown, including fenced
  ` ```mermaid ` blocks if you want a diagram).

Example:

```
Markdown Investigation summary
# Investigation summary

Found the bug in `file_watch.py` line 42.
```

The resulting widget shows a **"Save As"** button in place of "Open"
(there's nothing to "open" — its content already comes from this
file, not a chosen path): saving defaults to the project root, with a
filename derived from the *rendered content's own first line*
(kebab-case-slugified, e.g. `# Investigation summary` becomes
`investigation-summary.md`) — not from `<label>` above. Saving opens
the new file in a separate, ordinary Markdown widget instance; this
tempui-bound instance stays open, unaffected. See
`markdown-rendering.md`.

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
OPEN_MARKDOWN_KEYWORD = "OpenMarkdown"
SCRATCH_KEYWORD = "Scratch"
MARKDOWN_KEYWORD = "Markdown"
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
    """"question" (the original, default type), "lightning_round",
    "open_markdown", "scratch", or "markdown_content", read from the
    first non-blank line's keyword -- lets a caller that's seeing a
    temp-ui file for the first time (a notification, a saved Desk's
    widget state) know which widget kind to place without assuming
    "question". Named "markdown_content" (not "markdown") to stay
    unambiguous against the "markdown" *widget id* it happens to
    render into (TODO 9743419)."""
    for line in text.splitlines():
        if line.strip():
            keyword = line.split(None, 1)[0]
            if keyword == LIGHTNING_ROUND_KEYWORD:
                return "lightning_round"
            if keyword == OPEN_MARKDOWN_KEYWORD:
                return "open_markdown"
            if keyword == SCRATCH_KEYWORD:
                return "scratch"
            if keyword == MARKDOWN_KEYWORD:
                return "markdown_content"
            return "question"
    return "question"


def parse_open_markdown(text: str) -> str | None:
    """Extracts the target Markdown path from an OpenMarkdown temp-UI
    file's first line (`OpenMarkdown <path>`) -- same "everything after
    the first space is one opaque value" shape as Question, so a path
    containing spaces doesn't need escaping. Returns None if the file
    doesn't actually start with the OpenMarkdown keyword."""
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if parts[0] == OPEN_MARKDOWN_KEYWORD and len(parts) > 1:
            return parts[1].strip()
        return None
    return None


def parse_scratch(text: str) -> tuple[str, str] | None:
    """Extracts `(label, body)` from a Scratch temp-UI file: the first
    line is `Scratch <label>`; every line after it, verbatim (not
    further parsed), is the initial body text. Returns None if the file
    doesn't actually start with the Scratch keyword."""
    lines = text.splitlines()
    if not lines:
        return None
    parts = lines[0].split(None, 1)
    if not parts or parts[0] != SCRATCH_KEYWORD:
        return None
    label = parts[1].strip() if len(parts) > 1 else ""
    body = "\n".join(lines[1:])
    return label, body


def parse_markdown_tempui(text: str) -> tuple[str, str] | None:
    """Extracts `(label, content)` from a Markdown temp-UI file (TODO
    9743419): the first line is `Markdown <label>`; every line after
    it, verbatim, is the markdown content to render. Same shape as
    parse_scratch -- `label` is for notification text only, never used
    for the eventual saved filename (that's derived from `content`'s
    own first line, at save time). Returns None if the file doesn't
    actually start with the Markdown keyword."""
    lines = text.splitlines()
    if not lines:
        return None
    parts = lines[0].split(None, 1)
    if not parts or parts[0] != MARKDOWN_KEYWORD:
        return None
    label = parts[1].strip() if len(parts) > 1 else ""
    content = "\n".join(lines[1:])
    return label, content


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
