"""Materializes a tempui-DSL-defined custom widget's (TODO 91b3f42,
desk.temp_ui.CustomWidgetDefinition) base64-encoded HTML onto disk, so
it can be served exactly like any other `kind: "html"` widget (see
desk.server.runner.ServerHandle.mount_html_widget /
desk.shell.chromium_widget.ChromiumWidget). This is a disposable cache,
not a source of truth -- the actual source is whichever `DefineWidget`
tempui file or `.desk` file entry the definition came from, and this
gets regenerated fresh every time a definition is (re-)registered."""

import base64
import binascii
import logging
from pathlib import Path

from desk.temp_ui import CustomWidgetDefinition

logger = logging.getLogger(__name__)

CUSTOM_WIDGETS_CACHE_DIRNAME = "custom_widgets"


def materialized_widget_dir(desk_temp_dir: Path, keyword: str) -> Path:
    return desk_temp_dir / CUSTOM_WIDGETS_CACHE_DIRNAME / keyword


def materialize(desk_temp_dir: Path, definition: CustomWidgetDefinition) -> Path | None:
    """Decodes `definition.html_b64` to a real index.html at
    materialized_widget_dir(desk_temp_dir, definition.keyword),
    creating directories as needed, and returns that directory. Returns
    None (logged, not raised) if the base64/UTF-8 content is malformed
    -- one bad definition shouldn't take down the whole app."""
    target_dir = materialized_widget_dir(desk_temp_dir, definition.keyword)
    try:
        html = base64.b64decode(definition.html_b64.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        logger.error(
            "Failed to decode custom widget %r's html_b64 -- malformed base64/UTF-8",
            definition.keyword,
            exc_info=True,
        )
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "index.html").write_text(html)
    return target_dir
