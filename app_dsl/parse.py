"""Parses and validates an app-structure DSL definition (a single JSON
file -- see README.md) into the dataclasses in schema.py. Every
failure raises schema.DslError with a message naming the exact
problem (a missing key, a bad `type` discriminant, a reference to an
undeclared component/state slot/handler) -- never a bare KeyError/
TypeError, so build.py's caller gets one clean line, not a
traceback."""

import json

from schema import (
    AppDefinition,
    CallAction,
    ComponentEntry,
    DslError,
    EventWiringEntry,
    HandlerRef,
    LayoutDefinition,
    SplitLayoutNode,
    StateMutationAction,
    StateSlot,
    WindowEntry,
)

VALID_SPLIT_NODE_TYPES = ("hsplit", "vsplit", "pane")
VALID_LAYOUT_TYPES = ("split", "windowed")


def _require_dict(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise DslError(f"{where} must be a JSON object, got {type(value).__name__}")
    return value


def _require_list(value, where: str) -> list:
    if not isinstance(value, list):
        raise DslError(f"{where} must be a JSON array, got {type(value).__name__}")
    return value


def _require_str(d: dict, key: str, where: str) -> str:
    value = d.get(key)
    if not isinstance(value, str) or not value:
        raise DslError(f"{where}.{key} must be a non-empty string")
    return value


def _optional_float(d: dict, key: str, where: str) -> float | None:
    value = d.get(key)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise DslError(f"{where}.{key} must be a number if present")
    return float(value)


def _optional_str(d: dict, key: str, where: str) -> str | None:
    value = d.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise DslError(f"{where}.{key} must be a non-empty string if present")
    return value


def _parse_components(raw) -> list[ComponentEntry]:
    entries = []
    seen_tags = set()
    for i, item in enumerate(_require_list(raw, "components")):
        where = f"components[{i}]"
        d = _require_dict(item, where)
        tag = _require_str(d, "tag", where)
        source = _require_str(d, "source", where)
        class_name = _optional_str(d, "class_name", where)
        if tag in seen_tags:
            raise DslError(f"{where}: duplicate component tag {tag!r}")
        seen_tags.add(tag)
        entries.append(ComponentEntry(tag=tag, source=source, class_name=class_name))
    return entries


def _parse_split_node(raw, where: str, known_tags: set[str]) -> SplitLayoutNode:
    d = _require_dict(raw, where)
    node_type = _require_str(d, "type", where)
    if node_type not in VALID_SPLIT_NODE_TYPES:
        raise DslError(f"{where}.type must be one of {VALID_SPLIT_NODE_TYPES}, got {node_type!r}")
    min_size = _optional_float(d, "min_size", where)
    max_size = _optional_float(d, "max_size", where)
    if node_type == "pane":
        widget = _require_str(d, "widget", where)
        if widget not in known_tags:
            raise DslError(f"{where}.widget references undeclared component {widget!r}")
        return SplitLayoutNode(type=node_type, widget=widget, min_size=min_size, max_size=max_size)
    children_raw = _require_list(d.get("children", []), f"{where}.children")
    if not children_raw:
        raise DslError(f"{where}: a {node_type!r} node needs at least one child")
    children = [
        _parse_split_node(child, f"{where}.children[{i}]", known_tags)
        for i, child in enumerate(children_raw)
    ]
    return SplitLayoutNode(type=node_type, children=children, min_size=min_size, max_size=max_size)


def _parse_layout(raw, known_tags: set[str]) -> LayoutDefinition:
    where = "layout"
    d = _require_dict(raw, where)
    layout_type = _require_str(d, "type", where)
    if layout_type not in VALID_LAYOUT_TYPES:
        raise DslError(f"{where}.type must be one of {VALID_LAYOUT_TYPES}, got {layout_type!r}")
    if layout_type == "split":
        variants_raw = _require_dict(d.get("variants", {}), f"{where}.variants")
        if not variants_raw:
            raise DslError(f"{where}.variants must declare at least one layout variant")
        variants = {
            name: _parse_split_node(tree, f"{where}.variants.{name}", known_tags)
            for name, tree in variants_raw.items()
        }
        default_variant = _require_str(d, "default_variant", where)
        if default_variant not in variants:
            raise DslError(
                f"{where}.default_variant {default_variant!r} is not one of the declared variants {sorted(variants)}"
            )
        return LayoutDefinition(type=layout_type, variants=variants, default_variant=default_variant)
    windows_raw = _require_list(d.get("windows", []), f"{where}.windows")
    windows = []
    for i, item in enumerate(windows_raw):
        wwhere = f"{where}.windows[{i}]"
        wd = _require_dict(item, wwhere)
        widget = _require_str(wd, "widget", wwhere)
        if widget not in known_tags:
            raise DslError(f"{wwhere}.widget references undeclared component {widget!r}")
        windows.append(
            WindowEntry(
                widget=widget,
                x=_optional_float(wd, "x", wwhere) or 0.0,
                y=_optional_float(wd, "y", wwhere) or 0.0,
                width=_optional_float(wd, "width", wwhere) or 0.0,
                height=_optional_float(wd, "height", wwhere) or 0.0,
            )
        )
    return LayoutDefinition(type=layout_type, windows=windows)


def _parse_state(raw) -> list[StateSlot]:
    slots = []
    seen_names = set()
    for i, item in enumerate(_require_list(raw, "state")):
        where = f"state[{i}]"
        d = _require_dict(item, where)
        name = _require_str(d, "name", where)
        slot_type = _require_str(d, "type", where)
        if name in seen_names:
            raise DslError(f"{where}: duplicate state slot name {name!r}")
        seen_names.add(name)
        slots.append(StateSlot(name=name, type=slot_type, default=d.get("default")))
    return slots


def _parse_handlers(raw) -> dict[str, HandlerRef]:
    handlers = {}
    for name, item in _require_dict(raw, "handlers").items():
        where = f"handlers.{name}"
        d = _require_dict(item, where)
        module = _require_str(d, "module", where)
        export = _require_str(d, "export", where)
        handlers[name] = HandlerRef(module=module, export=export)
    return handlers


def _parse_action(raw, where: str, known_tags: set[str], known_state: set[str], known_handlers: set[str]):
    d = _require_dict(raw, where)
    if "set" in d:
        target = _require_str(d, "set", where)
        if target not in known_state:
            raise DslError(f"{where}.set references undeclared state slot {target!r}")
        source_expr = _require_str(d, "from", where)
        return StateMutationAction(target=target, source_expr=source_expr)
    if "call" in d:
        target = _require_str(d, "call", where)
        if target.startswith("escape:"):
            handler_name = target[len("escape:") :]
            if handler_name not in known_handlers:
                raise DslError(f"{where}.call references undeclared handler {target!r}")
        elif target not in known_tags:
            raise DslError(f"{where}.call references undeclared component {target!r}")
        method = _require_str(d, "method", where)
        args_raw = d.get("args", [])
        args = _require_list(args_raw, f"{where}.args")
        for i, arg in enumerate(args):
            if not isinstance(arg, str):
                raise DslError(f"{where}.args[{i}] must be a string (a JS/TS expression)")
        return CallAction(target=target, method=method, args=list(args))
    raise DslError(f"{where} must have either a 'set' or a 'call' key")


def _parse_events(
    raw, known_tags: set[str], known_state: set[str], known_handlers: set[str]
) -> list[EventWiringEntry]:
    entries = []
    for i, item in enumerate(_require_list(raw, "events")):
        where = f"events[{i}]"
        d = _require_dict(item, where)
        event = _require_str(d, "event", where)
        emitter = _require_str(d, "from", where)
        if emitter not in known_tags:
            raise DslError(f"{where}.from references undeclared component {emitter!r}")
        actions_raw = _require_list(d.get("actions", []), f"{where}.actions")
        if not actions_raw:
            raise DslError(f"{where}.actions must have at least one action")
        actions = [
            _parse_action(action, f"{where}.actions[{j}]", known_tags, known_state, known_handlers)
            for j, action in enumerate(actions_raw)
        ]
        entries.append(EventWiringEntry(event=event, emitter=emitter, actions=actions))
    return entries


def parse_app_definition(json_text: str) -> AppDefinition:
    try:
        raw = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise DslError(f"not valid JSON: {e}") from e
    top = _require_dict(raw, "<root>")

    components = _parse_components(top.get("components", []))
    known_tags = {c.tag for c in components}

    state = _parse_state(top.get("state", []))
    known_state = {s.name for s in state}

    handlers = _parse_handlers(top.get("handlers", {}))
    known_handlers = set(handlers)

    layout = _parse_layout(top["layout"], known_tags) if "layout" in top else None
    events = _parse_events(top.get("events", []), known_tags, known_state, known_handlers)

    return AppDefinition(
        components=components, layout=layout, events=events, state=state, handlers=handlers
    )
