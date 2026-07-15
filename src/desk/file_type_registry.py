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

from dataclasses import dataclass, field

FILE_TYPE_REGISTRY_UPDATED_EVENT = "desk.file_type_registry.updated"

ROLES = ("view", "edit", "consume", "produce")


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
