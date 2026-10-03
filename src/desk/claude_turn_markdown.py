"""Renders one Claude (Desk) turn as markdown (TODO 6ff3be8). Pure: takes the
turn's history entries, returns the text plus the images it references (the
caller writes the files). See plans/claude-desk-markdown-view-button.md.
"""
import time
from dataclasses import dataclass, field

from desk.claude_tool_result import IMAGE_SENTINEL, ImageAttachment, plain

IMAGES_DIRNAME = "images"


@dataclass
class RenderedTurn:
    markdown: str
    # image file name (relative to IMAGES_DIRNAME) -> attachment to write
    images: dict[str, ImageAttachment] = field(default_factory=dict)


def _fence(text: str) -> str:
    """A backtick fence longer than any backtick run inside `text`."""
    longest = run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def _fenced(text: str) -> str:
    fence = _fence(text)
    return f"{fence}\n{text}\n{fence}"


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def render_turn(entries: list, image_name) -> RenderedTurn:
    """`entries`: HistoryEntry-like objects (`.meta.kind/.ts/.turn_id`,
    `.text`, `.images`), already filtered to one turn, in order.
    `image_name(attachment) -> str` gives the file name each image will be
    saved under (the caller owns naming/saving)."""
    rendered = RenderedTurn(markdown="")
    first = entries[0] if entries else None
    turn_id = first.meta.turn_id if first is not None else None
    heading = "# Turn" if turn_id is None else f"# Turn {turn_id}"
    if first is not None:
        heading += f"\n\n*{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(first.meta.ts))}*"
    blocks = [heading]
    for entry in entries:
        kind = entry.meta.kind
        text = entry.text
        if kind in ("user", "queued"):
            blocks.append(_blockquote(plain(text)))
        elif kind == "assistant":
            blocks.append(plain(text))
        elif kind == "tool":
            blocks.append("**Tool**\n\n" + _fenced(text))
        elif kind in ("tool_result", "tool_error"):
            label = "**Error**" if kind == "tool_error" else "**Result**"
            blocks.append(f"{label}\n\n" + _result_body(text, entry.images, image_name, rendered))
        elif kind == "error":
            blocks.append("**Error**\n\n" + _fenced(text))
        else:
            blocks.append(f"*{plain(text)}*")
    rendered.markdown = "\n\n".join(blocks) + "\n"
    return rendered


def _result_body(text: str, images: list[ImageAttachment], image_name, rendered: RenderedTurn) -> str:
    """Text segments fenced, each image between them as a real markdown image
    (it can't render inside a code fence)."""
    out = []
    for index, segment in enumerate(text.split(IMAGE_SENTINEL)):
        if index:
            attachment = images[index - 1] if index - 1 < len(images) else None
            if attachment is not None and attachment.data is not None:
                name = image_name(attachment)
                rendered.images[name] = attachment
                out.append(f"![image]({IMAGES_DIRNAME}/{name})")
            else:
                out.append("*[image unavailable]*")
        segment = segment.strip("\n")
        if segment:
            out.append(_fenced(segment))
    return "\n\n".join(out) if out else _fenced("")
