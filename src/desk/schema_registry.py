"""The state store's runtime-only schema registry (TODO af7898b) -- which
desk.state.* key currently has an active schema, its source widget id,
and whether it's permanently enforced (a built-in widget) or tracked by
which placed widget instances are keeping it active (a tempui-sourced
custom widget). Never persisted: everything that populates it is already
re-walked on every Desk open/switch anyway (built-ins via
discover_widgets/hot-reload, tempui-sourced ones via placement/restore),
so it's simply rebuilt fresh each time -- the same
lock-protected-runtime-class shape desk.event_mediator.EventMediator
already is (constructed once per server run, shared between the Bridge
API routes and DeskWindow). See plans/state-store-schema-core.md."""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from desk.schema_types import SchemaSyntaxError, TypeNode, parse_type_expression, type_expressions_equivalent


class SchemaConflict(Exception):
    pass


@dataclass
class RegisteredSchema:
    key: str
    type_expr: str
    type_node: TypeNode
    source_widget_id: str
    permanent: bool
    placed_instance_ids: set[str] = field(default_factory=set)


class SchemaRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._schemas: dict[str, RegisteredSchema] = {}

    def get(self, key: str) -> RegisteredSchema | None:
        with self._lock:
            return self._schemas.get(key)

    def permanent_source_ids(self) -> set[str]:
        """Every source_widget_id that currently owns at least one
        permanent entry -- used by DeskWindow._refresh_builtin_schemas
        to clear every previously-registered built-in schema before a
        fresh re-registration pass, including one whose widget has since
        been removed from disk entirely (and so wouldn't otherwise
        appear in a freshly re-discovered widget catalog to clear
        against)."""
        with self._lock:
            return {schema.source_widget_id for schema in self._schemas.values() if schema.permanent}

    def clear_source(self, source_widget_id: str) -> None:
        """Drops every permanent entry `source_widget_id` registered --
        called before a fresh built-in re-registration pass (hot reload
        or startup), so a schema a widget author just removed (or a
        widget that's been deleted) doesn't linger forever, and a
        conflict that's been fixed on disk correctly clears. Never
        touches a non-permanent (tempui-sourced) entry -- those are
        maintained entirely through join_or_conflict_placement's own
        lazy pruning, regardless of which widget kind currently owns
        them."""
        with self._lock:
            for key in [k for k, schema in self._schemas.items() if schema.permanent and schema.source_widget_id == source_widget_id]:
                del self._schemas[key]

    def register_permanent(self, key: str, type_expr: str, source_widget_id: str) -> None:
        """Raises SchemaSyntaxError if `type_expr` doesn't parse, or
        SchemaConflict if a different schema (permanent or
        still-active-tempui) already claims `key`. Idempotent for the
        exact same (key, type_expr, source_widget_id) triple."""
        type_node = parse_type_expression(type_expr)
        with self._lock:
            existing = self._schemas.get(key)
            if existing is not None:
                if existing.source_widget_id == source_widget_id and existing.permanent:
                    existing.type_expr = type_expr
                    existing.type_node = type_node
                    return
                if not self._is_dormant(existing) and not type_expressions_equivalent(existing.type_expr, type_expr):
                    raise SchemaConflict(
                        f"State key {key!r}: schema from {source_widget_id!r} ({type_expr!r}) conflicts with "
                        f"the schema already registered by {existing.source_widget_id!r} ({existing.type_expr!r})"
                    )
            self._schemas[key] = RegisteredSchema(
                key=key, type_expr=type_expr, type_node=type_node, source_widget_id=source_widget_id, permanent=True
            )

    def join_or_conflict_placement(
        self,
        key: str,
        type_expr: str,
        source_widget_id: str,
        instance_id: str,
        is_instance_placed: Callable[[str], bool],
    ) -> None:
        """Raises SchemaSyntaxError if `type_expr` doesn't parse, or
        SchemaConflict on a genuine conflict. Performs lazy maintenance
        on any existing entry's placed_instance_ids (pruning ids
        `is_instance_placed` reports as no longer placed) before
        deciding dormant-vs-active, per the "lazy pruning only" design
        decision."""
        type_node = parse_type_expression(type_expr)
        with self._lock:
            existing = self._schemas.get(key)
            if existing is None:
                self._schemas[key] = RegisteredSchema(
                    key=key,
                    type_expr=type_expr,
                    type_node=type_node,
                    source_widget_id=source_widget_id,
                    permanent=False,
                    placed_instance_ids={instance_id},
                )
                return

            if existing.permanent:
                if not type_expressions_equivalent(existing.type_expr, type_expr):
                    raise SchemaConflict(
                        f"State key {key!r}: schema from {source_widget_id!r} ({type_expr!r}) conflicts with "
                        f"the permanently-enforced schema registered by {existing.source_widget_id!r} "
                        f"({existing.type_expr!r})"
                    )
                return

            existing.placed_instance_ids = {i for i in existing.placed_instance_ids if is_instance_placed(i)}

            if existing.placed_instance_ids:
                if not type_expressions_equivalent(existing.type_expr, type_expr):
                    raise SchemaConflict(
                        f"State key {key!r}: schema from {source_widget_id!r} ({type_expr!r}) conflicts with "
                        f"the schema already active from {existing.source_widget_id!r} ({existing.type_expr!r})"
                    )
                existing.placed_instance_ids.add(instance_id)
                return

            # Dormant: no placed instance currently references it.
            if type_expressions_equivalent(existing.type_expr, type_expr):
                existing.placed_instance_ids.add(instance_id)
            else:
                self._schemas[key] = RegisteredSchema(
                    key=key,
                    type_expr=type_expr,
                    type_node=type_node,
                    source_widget_id=source_widget_id,
                    permanent=False,
                    placed_instance_ids={instance_id},
                )

    @staticmethod
    def _is_dormant(schema: RegisteredSchema) -> bool:
        return not schema.permanent and not schema.placed_instance_ids
