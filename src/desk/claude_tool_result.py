"""Flattening of tool-result content for the Claude (Desk) widget (TODO
10b4d7d). See plans/claude-desk-top-level-tool-results.md.

`ToolResultBlock.content` is a string, a list of content dicts (`{"type":
"text", "text"}`, `{"type": "image", "source": {...}}`, ...) or None. The
flattened text carries one IMAGE_SENTINEL per image (never the literal text
"[image]", so a result that happens to contain that string can't be mistaken
for a placeholder); the original images are kept alongside as
`ImageAttachment`s, in sentinel order.
"""
import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

IMAGE_SENTINEL = "￼"  # U+FFFC OBJECT REPLACEMENT CHARACTER
IMAGE_PLACEHOLDER = "[image]"
NO_OUTPUT_TEXT = "(no output)"

_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


@dataclass
class ImageAttachment:
    media_type: str = "image/png"
    data: bytes | None = None  # decoded bytes for a base64 source
    url: str | None = None  # for a url source -- shown, never fetched

    def extension(self) -> str:
        return _EXTENSIONS.get(self.media_type, ".img")


def flatten_tool_result(content: object) -> tuple[str, list[ImageAttachment]]:
    """(text with IMAGE_SENTINELs, images in sentinel order)."""
    images: list[ImageAttachment] = []
    if content is None:
        return NO_OUTPUT_TEXT, images
    if isinstance(content, str):
        return (content if content != "" else NO_OUTPUT_TEXT), images
    if not isinstance(content, list):
        return str(content), images
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            parts.append(str(block))
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append(str(block.get("text", "")))
        elif kind == "image":
            source = block.get("source") or {}
            if source.get("type") == "base64":
                try:
                    data = base64.b64decode(source.get("data", ""))
                except (ValueError, TypeError):
                    data = None
                images.append(ImageAttachment(media_type=source.get("media_type", "image/png"), data=data))
                parts.append(IMAGE_SENTINEL)
            elif source.get("type") == "url" and source.get("url"):
                # Never fetched: just say where it is.
                parts.append(f"[image: {source['url']}]")
            else:
                parts.append(IMAGE_PLACEHOLDER)
        else:
            parts.append(f"[{kind or 'unknown'}]")
    text = "\n".join(part for part in parts if part != "")
    return (text if text != "" else NO_OUTPUT_TEXT), images


def plain(text: str) -> str:
    """The sentinel rendered as the readable placeholder."""
    return text.replace(IMAGE_SENTINEL, IMAGE_PLACEHOLDER)


def save_image(directory: Path, image: ImageAttachment) -> Path | None:
    """Writes `image`'s bytes under `directory`, named by content hash
    (idempotent: the same image always lands at the same path). None if
    the attachment has no bytes (undecodable, or a url source)."""
    if image.data is None:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (hashlib.sha256(image.data).hexdigest()[:16] + image.extension())
    if not path.exists():
        path.write_bytes(image.data)
    return path
