"""Parsing/rendering for a QUESTIONS.md-shaped file -- shared by the
Questions widget (widgets/questions/). See plans/questions-widget.md.

Mirrors desk.todo_file's shape (dataclass + regex-based parser +
renderer), adapted for QUESTIONS.md's actual structure: each entry is a
`## TODO \\`<id>\\`[/\\`<id2>\\`...]: <summary>` heading (one or more TODO
ids, not exactly one like TODO.md's own items), followed by free-form
body prose, followed by a `(Answer: ...)` block. Answers are written in
free-form prose and can legitimately contain their own parentheses
(confirmed directly against this project's own QUESTIONS.md, e.g. "option
(a)"), so finding the end of an answer can't just look for the first
`)` after `(Answer:` -- it has to track paren depth to find the one that
actually matches."""
import re
from dataclasses import dataclass
from pathlib import Path

QUESTIONS_FILENAME = "QUESTIONS.md"

ENTRY_START_RE = re.compile(r"^## TODO\b.*$", re.MULTILINE)
TODO_ID_RE = re.compile(r"`([0-9a-f]{7})`")
ANSWER_START_RE = re.compile(r"^\(Answer:", re.MULTILINE)


@dataclass
class QuestionEntry:
    todo_ids: list[str]
    title: str  # the heading text after "## " (e.g. "TODO `9743419`: ...")
    body: str  # the free-form question text between the heading and the
    # "(Answer: ...)" block, stripped
    answer: str  # "" if not yet answered
    raw_text: str  # exact original text (including its own "## " heading
    # line and "(Answer: ...)" block), preserved verbatim


def find_nearest_questions_file(start_dir: Path) -> Path | None:
    """Searches start_dir and its parents (in that order) for a
    QUESTIONS.md -- same walk-up-directories convention as
    desk.todo_file.find_nearest_todo_file."""
    for directory in (start_dir, *start_dir.parents):
        candidate = directory / QUESTIONS_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _find_matching_close_paren(text: str, open_index: int) -> int | None:
    """`text[open_index]` must be '('. Returns the index of the ')' that
    closes it (tracking nested parens in between), or None if
    unbalanced."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


def _split_entry(raw_text: str) -> tuple[str, str, str]:
    """Splits one entry's raw_text into (title, body, answer). Every
    entry produced by this project's own workflow always has a
    "(Answer: ...)" block (even if empty), so title/body are only ever
    parsed relative to it; an entry missing one entirely (malformed,
    hand-edited) is treated as having no answer and its whole remainder
    as body, rather than guessing further."""
    heading_line, _, rest = raw_text.partition("\n")
    title = heading_line.removeprefix("##").strip()

    answer_start = ANSWER_START_RE.search(rest)
    if answer_start is None:
        return title, rest.strip(), ""

    open_index = answer_start.start()  # the "(" itself
    close_index = _find_matching_close_paren(rest, open_index)
    if close_index is None:
        return title, rest.strip(), ""

    body = rest[: answer_start.start()].strip()
    answer = rest[answer_start.end() : close_index].strip()
    return title, body, answer


def parse_questions_file(path: Path) -> tuple[str, list[QuestionEntry]]:
    """Returns (preamble_text, entries). preamble_text is everything
    before the first entry (title line, intro prose)."""
    text = path.read_text()
    starts = [m.start() for m in ENTRY_START_RE.finditer(text)]

    preamble = text[: starts[0]] if starts else text

    entries = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        raw_text = text[start:end]
        title, body, answer = _split_entry(raw_text)
        entries.append(
            QuestionEntry(
                todo_ids=TODO_ID_RE.findall(title),
                title=title,
                body=body,
                answer=answer,
                raw_text=raw_text,
            )
        )
    return preamble, entries


def render_questions_file(preamble: str, entries: list[QuestionEntry]) -> str:
    """Reassembles file text from a preamble plus entries in their
    current list order -- mirrors desk.todo_file.render_todo_file."""
    return preamble + "".join(entry.raw_text for entry in entries)


def with_answer(entry: QuestionEntry, new_answer: str) -> QuestionEntry:
    """Returns a new QuestionEntry with its answer replaced, splicing the
    new text into the exact span of the original "(Answer: ...)" block
    within raw_text so everything else (heading, body, surrounding
    blank lines) is left untouched."""
    heading_line, sep, rest = entry.raw_text.partition("\n")
    answer_start = ANSWER_START_RE.search(rest)
    if answer_start is None:
        raise ValueError(f"entry {entry.title!r} has no (Answer: ...) block to update")
    open_index = answer_start.start()
    close_index = _find_matching_close_paren(rest, open_index)
    if close_index is None:
        raise ValueError(f"entry {entry.title!r} has an unterminated (Answer: ...) block")

    new_rest = rest[: answer_start.end()] + f" {new_answer})" + rest[close_index + 1 :]
    raw_text = heading_line + sep + new_rest
    return QuestionEntry(
        todo_ids=entry.todo_ids,
        title=entry.title,
        body=entry.body,
        answer=new_answer,
        raw_text=raw_text,
    )
