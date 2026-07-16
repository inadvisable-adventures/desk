"""The file type registry (TODO b5d52c0): maps file types -- by
extension and/or MIME type -- to the widget(s) that can view, edit,
consume, or produce that type. Generalizes the small hardcoded
EXTERNAL_DROP_WIDGET_BY_SUFFIX map in desk.shell.window into something
dynamic and user/agent-editable, persisted on the Desk dataclass/.desk
file (desk.desks) the same way CustomWidgetDefinition already is.

Edited/read entirely through the Bridge API (kind:"html" widgets, see
desk.server.app's filetypes routes) or a current_context hook (kind:
"python" widgets, see desk.shell.window.DeskWindow
.get_file_type_registry_dicts/current_context
.get_file_type_registry_provider) -- never by reading/writing the
.desk file directly."""

import mimetypes
from dataclasses import dataclass, field
from pathlib import Path

FILE_TYPE_REGISTRY_UPDATED_EVENT = "desk.file_type_registry.updated"

ROLES = ("view", "edit", "git-diff", "consume", "produce")


@dataclass
class FileTypeHandler:
    widget_id: str
    role: str  # one of ROLES


@dataclass
class FileTypeRegistryEntry:
    extensions: list[str] = field(default_factory=list)  # e.g. [".svg"]
    mime_types: list[str] = field(default_factory=list)  # e.g. ["image/svg+xml"]
    handlers: list[FileTypeHandler] = field(default_factory=list)


def handler_to_dict(handler: FileTypeHandler) -> dict:
    return {"widget_id": handler.widget_id, "role": handler.role}


def handler_from_dict(data: dict) -> FileTypeHandler:
    return FileTypeHandler(widget_id=data["widget_id"], role=data["role"])


def entry_to_dict(entry: FileTypeRegistryEntry) -> dict:
    return {
        "extensions": list(entry.extensions),
        "mime_types": list(entry.mime_types),
        "handlers": [handler_to_dict(h) for h in entry.handlers],
    }


def entry_from_dict(data: dict) -> FileTypeRegistryEntry:
    return FileTypeRegistryEntry(
        extensions=list(data.get("extensions", [])),
        mime_types=list(data.get("mime_types", [])),
        handlers=[handler_from_dict(h) for h in data.get("handlers", [])],
    )


# TODO efdad99: generalizes desk.shell.window.EXTERNAL_DROP_WIDGET_BY_SUFFIX
# (kept as a code-level floor, not replaced by it) plus raster image
# suffixes (desk.shell.window.IMAGE_DROP_SUFFIXES) -- so existing
# double-click behavior for these already-known types doesn't regress
# just because a fresh Desk's dynamic registry starts out empty.
BUILTIN_VIEW_WIDGET_BY_SUFFIX = {
    ".md": "markdown",
    ".svg": "image_viewer",
    ".svgz": "image_viewer",
    ".png": "image_viewer",
    ".jpg": "image_viewer",
    ".jpeg": "image_viewer",
    ".gif": "image_viewer",
    ".bmp": "image_viewer",
    ".webp": "image_viewer",
    ".tif": "image_viewer",
    ".tiff": "image_viewer",
    ".ico": "image_viewer",
}


# TODO 7076af5: a built-in *edit* fallback, mirroring
# BUILTIN_VIEW_WIDGET_BY_SUFFIX above -- without this, clicking Edit on
# a .svg would keep opening it in the plain text Editor by default
# (looks_like_text_file says yes -- SVG is valid UTF-8 XML) even after a
# dedicated SVG Editor widget exists, the same regression-in-usefulness
# find_view_handler's own builtin fallback was added to avoid.
BUILTIN_EDIT_WIDGET_BY_SUFFIX = {
    ".svg": "svg_editor",
}


def _find_handler(registry: list[FileTypeRegistryEntry], path: Path, role: str) -> str | None:
    """Extension match first (case-insensitive), then MIME type
    (mimetypes.guess_type) -- "keyed by both," per the original ask."""
    suffix = path.suffix.lower()
    mime_type, _ = mimetypes.guess_type(str(path))
    for entry in registry:
        extensions = {ext.lower() for ext in entry.extensions}
        if suffix in extensions or (mime_type is not None and mime_type in entry.mime_types):
            for handler in entry.handlers:
                if handler.role == role:
                    return handler.widget_id
    return None


def find_view_handler(registry: list[FileTypeRegistryEntry], path: Path) -> str | None:
    """A registered `"view"` handler for `path`'s type, falling back to
    `BUILTIN_VIEW_WIDGET_BY_SUFFIX` if the dynamic registry has nothing
    -- see TODO efdad99."""
    return _find_handler(registry, path, "view") or BUILTIN_VIEW_WIDGET_BY_SUFFIX.get(path.suffix.lower())


def find_edit_handler(registry: list[FileTypeRegistryEntry], path: Path) -> str | None:
    """A registered `"edit"` handler for `path`'s type, falling back to
    `BUILTIN_EDIT_WIDGET_BY_SUFFIX` (TODO 7076af5) if the dynamic
    registry has nothing. Still no fallback beyond that: the caller
    (TODO efdad99) decides what happens for a genuinely text file with
    no edit handler at all (the built-in text Editor widget), which
    isn't this function's concern."""
    return _find_handler(registry, path, "edit") or BUILTIN_EDIT_WIDGET_BY_SUFFIX.get(path.suffix.lower())


# TODO fd713a5: unlike view/edit (suffix-specific -- an .svg needs a
# different viewer than a .png), git diff is meaningful for *any* file
# type at all, so this is a single unconditional fallback widget id,
# not a suffix-keyed dict.
GIT_DIFF_WIDGET_ID = "git_diff"


def find_git_diff_handler(registry: list[FileTypeRegistryEntry], path: Path) -> str:
    """A registered `"git-diff"` handler for `path`'s type, falling back
    to the built-in Git Diff Viewer widget (`GIT_DIFF_WIDGET_ID`) if the
    dynamic registry has nothing. Unlike `find_view_handler`/
    `find_edit_handler`, always resolves to a real widget id (never
    `None`) -- there's no "nothing can handle this" case for git diff,
    it applies regardless of file type."""
    return _find_handler(registry, path, "git-diff") or GIT_DIFF_WIDGET_ID


def looks_like_text_file(path: Path, sniff_bytes: int = 8192) -> bool:
    """A null-byte + UTF-8-decodability sniff on the first
    `sniff_bytes` -- a self-contained heuristic (no new dependency, per
    CLAUDE.md) that correctly treats an unknown-extension text file (a
    Dockerfile, a dotfile) as text and a real binary as not, unlike a
    fixed extension allowlist. `False` (not text) for anything
    unreadable, matching this codebase's general "can't tell -> don't
    guess yes" posture for file-type detection (TODO efdad99)."""
    try:
        with path.open("rb") as f:
            chunk = f.read(sniff_bytes)
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
