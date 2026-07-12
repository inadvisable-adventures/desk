"""Read/write format for the Stack widget's export/import (TODO
ac212bc): a `# Stack` title line, then one `## <title>` heading per
frame followed by its notes, bottom-of-stack (oldest, pushed first) to
top (current) reading top-to-bottom -- narrates the nesting in the
order it actually happened, like a written log, rather than most
-recent-first."""

from dataclasses import dataclass

STACK_TITLE = "# Stack"
FRAME_HEADING_PREFIX = "## "


@dataclass
class StackFrame:
    title: str
    notes: str = ""


def render_stack_file(frames: list[StackFrame]) -> str:
    lines = [STACK_TITLE, ""]
    for frame in frames:
        lines.append(f"{FRAME_HEADING_PREFIX}{frame.title}")
        lines.append("")
        if frame.notes:
            lines.append(frame.notes)
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def parse_stack_file(text: str) -> list[StackFrame]:
    """Inverse of render_stack_file -- splits on `## ` headings (each
    becomes one frame, in the same bottom-to-top order), ignoring
    everything before the first such heading (e.g. the `# Stack` title
    line)."""
    frames: list[StackFrame] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_title is not None:
            notes = "\n".join(current_lines).strip("\n")
            frames.append(StackFrame(title=current_title, notes=notes))

    for line in text.splitlines():
        if line.startswith(FRAME_HEADING_PREFIX):
            flush()
            current_title = line[len(FRAME_HEADING_PREFIX) :].strip()
            current_lines = []
        elif current_title is not None:
            current_lines.append(line)
    flush()
    return frames
