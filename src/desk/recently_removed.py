"""Shared constants for the Recently Removed feature (TODO 454d718). See
plans/recently-removed-widget.md."""

# Published by DeskWindow whenever a tombstone is added, revived or cleared:
# {"entries": [{"instance_id", "widget_id", "kind", "label", "removed_at"}]}
# newest first (the widget-local-storage `state` is deliberately left out).
RECENTLY_REMOVED_CHANGED_EVENT = "desk.recently_removed.changed"

# Newest-first tombstones kept in the .desk file; the oldest fall off.
RECENTLY_REMOVED_MAX = 20
