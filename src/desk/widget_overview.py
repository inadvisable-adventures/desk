"""Event name for the Open Widgets widget's live updates (TODO 53779f4).
Published by `DeskWindow` whenever a widget is placed/removed or an
instance's `[STALE]` bit flips; the payload is the full overview:
{"widgets": [{"instance_id", "widget_id", "title", "kind", "stale"}, ...]}
in placement order. See plans/open-widgets-widget.md."""

WIDGET_OVERVIEW_CHANGED_EVENT = "desk.widgets.overview_changed"
