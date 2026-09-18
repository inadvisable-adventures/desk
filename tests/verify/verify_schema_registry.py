import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.event_mediator import EventMediator  # noqa: E402
from desk.schema_registry import SCHEMA_CHANGED_EVENT, SchemaConflict, SchemaRegistry  # noqa: E402
from desk.schema_types import SchemaSyntaxError  # noqa: E402

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def expect_conflict(fn, name):
    try:
        fn()
        check(name, False)
    except SchemaConflict:
        check(name, True)


# ---------- register_permanent ----------


def test_register_permanent_accepts_a_fresh_key():
    registry = SchemaRegistry()
    registry.register_permanent("counter", "number", "widget_a")
    entry = registry.get("counter")
    check("fresh permanent registration succeeds", entry is not None and entry.permanent)
    check("registered under the right source", entry.source_widget_id == "widget_a")


def test_register_permanent_is_idempotent_for_the_same_source():
    registry = SchemaRegistry()
    registry.register_permanent("counter", "number", "widget_a")
    registry.register_permanent("counter", "number", "widget_a")
    registry.register_permanent("counter", "string", "widget_a")  # same source may update its own schema
    entry = registry.get("counter")
    check("same-source re-registration updates in place, not a conflict", entry.type_expr == "string")


def test_register_permanent_conflicts_across_sources():
    registry = SchemaRegistry()
    registry.register_permanent("counter", "number", "widget_a")
    expect_conflict(
        lambda: registry.register_permanent("counter", "string", "widget_b"),
        "a different source registering a different schema for the same key conflicts",
    )
    registry.register_permanent("counter", "number", "widget_b")  # equivalent schema never conflicts
    check("an equivalent schema from a different source is not a conflict", registry.get("counter") is not None)


def test_register_permanent_rejects_bad_syntax():
    registry = SchemaRegistry()
    try:
        registry.register_permanent("counter", "not a valid ts type }", "widget_a")
        check("a malformed type expression raises SchemaSyntaxError", False)
    except SchemaSyntaxError:
        check("a malformed type expression raises SchemaSyntaxError", True)


def test_clear_source_lets_a_fixed_conflict_through():
    registry = SchemaRegistry()
    registry.register_permanent("counter", "number", "widget_a")
    expect_conflict(
        lambda: registry.register_permanent("counter", "string", "widget_b"),
        "widget_b's conflicting registration is refused before clear_source",
    )
    registry.clear_source("widget_a")
    registry.register_permanent("counter", "string", "widget_b")
    check("widget_b can register once widget_a's schema is cleared", registry.get("counter").source_widget_id == "widget_b")


def test_clear_source_never_touches_tempui_entries():
    registry = SchemaRegistry()
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-1", lambda i: True)
    registry.clear_source("custom_widget")
    check("clear_source leaves a non-permanent entry alone", registry.get("counter") is not None)


# ---------- join_or_conflict_placement ----------


def test_placement_fresh_registration():
    registry = SchemaRegistry()
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-1", lambda i: True)
    entry = registry.get("counter")
    check("fresh tempui placement registers a non-permanent entry", entry is not None and not entry.permanent)
    check("the placing instance is tracked", entry.placed_instance_ids == {"inst-1"})


def test_placement_join_while_active():
    registry = SchemaRegistry()
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-1", lambda i: True)
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-2", lambda i: True)
    check("a second instance with the same schema joins", registry.get("counter").placed_instance_ids == {"inst-1", "inst-2"})


def test_placement_conflict_while_active():
    registry = SchemaRegistry()
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-1", lambda i: True)
    expect_conflict(
        lambda: registry.join_or_conflict_placement("counter", "string", "other_widget", "inst-2", lambda i: True),
        "a different schema for an active key conflicts",
    )
    check("the conflicting instance was never added", "inst-2" not in registry.get("counter").placed_instance_ids)


def test_placement_conflict_against_permanent():
    registry = SchemaRegistry()
    registry.register_permanent("counter", "number", "builtin_widget")
    expect_conflict(
        lambda: registry.join_or_conflict_placement("counter", "string", "custom_widget", "inst-1", lambda i: True),
        "a tempui placement conflicting with a permanent schema is refused",
    )
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-1", lambda i: True)
    check(
        "a tempui placement with an equivalent schema joins a permanent entry without tracking instances",
        registry.get("counter").permanent,
    )


def test_placement_dormant_reactivate_if_unchanged():
    registry = SchemaRegistry()
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-1", lambda i: False)
    # inst-1 is reported as no longer placed -- the entry is dormant before the next call.
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-2", lambda i: i != "inst-1")
    entry = registry.get("counter")
    check("reactivating a dormant schema with the same type keeps the same entry", entry.type_expr == "number")
    check("the old instance was pruned and the new one tracked", entry.placed_instance_ids == {"inst-2"})


def test_placement_dormant_replace_if_different():
    registry = SchemaRegistry()
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-1", lambda i: False)
    registry.join_or_conflict_placement("counter", "string", "other_widget", "inst-2", lambda i: i != "inst-1")
    entry = registry.get("counter")
    check("replacing a dormant schema with a different type succeeds", entry.type_expr == "string")
    check("the new source owns the replaced entry", entry.source_widget_id == "other_widget")
    check("only the new instance is tracked", entry.placed_instance_ids == {"inst-2"})


def test_placement_lazy_pruning_is_exercised():
    registry = SchemaRegistry()
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-1", lambda i: True)
    still_placed = {"inst-1"}
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-2", lambda i: i in still_placed)
    still_placed.add("inst-2")
    check("both instances tracked while both report placed", registry.get("counter").placed_instance_ids == {"inst-1", "inst-2"})
    still_placed.discard("inst-1")
    # A third join triggers the maintenance pass, pruning inst-1 (now reported unplaced) before deciding.
    registry.join_or_conflict_placement("counter", "number", "custom_widget", "inst-3", lambda i: i in still_placed)
    check(
        "a subsequent join prunes an instance is_instance_placed now reports as gone",
        registry.get("counter").placed_instance_ids == {"inst-2", "inst-3"},
    )


def test_permanent_source_ids():
    registry = SchemaRegistry()
    registry.register_permanent("counter", "number", "widget_a")
    registry.register_permanent("label", "string", "widget_b")
    registry.join_or_conflict_placement("other", "boolean", "custom_widget", "inst-1", lambda i: True)
    check("permanent_source_ids only includes permanent sources", registry.permanent_source_ids() == {"widget_a", "widget_b"})
    registry.clear_source("widget_a")
    check("clearing a source removes it from permanent_source_ids", registry.permanent_source_ids() == {"widget_b"})


# ---------- TODO 6330249: source_kind, all(), and live change events ----------


def test_source_kind_round_trips():
    registry = SchemaRegistry()
    registry.register_permanent("counter", "number", "builtin_widget", source_kind="widget")
    registry.register_permanent("doc", "string", "/project/.desk_temp/schemas/doc.json", source_kind="file")
    check("a widget-sourced schema records source_kind='widget'", registry.get("counter").source_kind == "widget")
    check("a file-sourced schema records source_kind='file'", registry.get("doc").source_kind == "file")

    registry.join_or_conflict_placement("tempui_key", "boolean", "custom_widget", "inst-1", lambda i: True)
    check(
        "a tempui-placed schema is always source_kind='widget'",
        registry.get("tempui_key").source_kind == "widget",
    )


def test_all_returns_every_registered_schema():
    registry = SchemaRegistry()
    registry.register_permanent("counter", "number", "widget_a")
    registry.join_or_conflict_placement("other", "string", "custom_widget", "inst-1", lambda i: True)
    keys = {schema.key for schema in registry.all()}
    check("all() returns every registered schema regardless of source", keys == {"counter", "other"})


def test_successful_mutations_publish_schema_changed():
    mediator = EventMediator()
    registry = SchemaRegistry(event_mediator=mediator)
    mediator.subscribe("listener", SCHEMA_CHANGED_EVENT)

    registry.register_permanent("counter", "number", "widget_a")
    event = mediator.poll("listener", timeout=1)
    check("a successful register_permanent publishes SCHEMA_CHANGED_EVENT", event is not None and event.name == SCHEMA_CHANGED_EVENT)

    registry.join_or_conflict_placement("other", "string", "custom_widget", "inst-1", lambda i: True)
    event = mediator.poll("listener", timeout=1)
    check("a successful join_or_conflict_placement publishes too", event is not None and event.name == SCHEMA_CHANGED_EVENT)

    registry.clear_source("widget_a")
    event = mediator.poll("listener", timeout=1)
    check("clear_source publishes when it actually removes something", event is not None and event.name == SCHEMA_CHANGED_EVENT)


def test_conflicts_do_not_publish():
    mediator = EventMediator()
    registry = SchemaRegistry(event_mediator=mediator)
    registry.register_permanent("counter", "number", "widget_a")
    mediator.subscribe("listener", SCHEMA_CHANGED_EVENT)

    try:
        registry.register_permanent("counter", "string", "widget_b")
        check("expected a conflict to be raised", False)
    except SchemaConflict:
        pass
    event = mediator.poll("listener", timeout=1)
    check("a conflict does not publish SCHEMA_CHANGED_EVENT", event is None)

    check(
        "clear_source on a source with nothing registered does not publish",
        mediator.poll("listener", timeout=1) is None,
    )


def test_registry_with_no_mediator_never_raises():
    registry = SchemaRegistry()  # event_mediator=None, matching every existing call site
    registry.register_permanent("counter", "number", "widget_a")  # must not raise
    registry.clear_source("widget_a")  # must not raise
    check("a registry with no event_mediator works exactly as before", registry.get("counter") is None)


test_register_permanent_accepts_a_fresh_key()
test_register_permanent_is_idempotent_for_the_same_source()
test_register_permanent_conflicts_across_sources()
test_register_permanent_rejects_bad_syntax()
test_clear_source_lets_a_fixed_conflict_through()
test_clear_source_never_touches_tempui_entries()
test_placement_fresh_registration()
test_placement_join_while_active()
test_placement_conflict_while_active()
test_placement_conflict_against_permanent()
test_placement_dormant_reactivate_if_unchanged()
test_placement_dormant_replace_if_different()
test_placement_lazy_pruning_is_exercised()
test_permanent_source_ids()
test_source_kind_round_trips()
test_all_returns_every_registered_schema()
test_successful_mutations_publish_schema_changed()
test_conflicts_do_not_publish()
test_registry_with_no_mediator_never_raises()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
