import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = "/Users/mphair/inadvisable-adventures/desk"
sys.path.insert(0, os.path.join(REPO_ROOT, "app_dsl"))

from parse import parse_app_definition  # noqa: E402
from schema import CallAction, DslError, StateMutationAction  # noqa: E402

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


REPRESENTATIVE_DEFINITION = {
    "components": [
        {"tag": "map-panel", "source": "map-panel.ts"},
        {"tag": "timeline-view", "source": "timeline-view.ts"},
        {"tag": "detail-view", "source": "detail-view.ts"},
    ],
    "state": [
        {"name": "selectedId", "type": "string | null", "default": None},
        {"name": "pinnedIds", "type": "string[]", "default": []},
    ],
    "layout": {
        "type": "split",
        "variants": {
            "default": {
                "type": "hsplit",
                "children": [
                    {"type": "pane", "widget": "map-panel", "min_size": 200},
                    {
                        "type": "vsplit",
                        "children": [
                            {"type": "pane", "widget": "timeline-view"},
                            {"type": "pane", "widget": "detail-view"},
                        ],
                    },
                ],
            }
        },
        "default_variant": "default",
    },
    "events": [
        {
            "event": "marker-selected",
            "from": "map-panel",
            "actions": [
                {"set": "selectedId", "from": "event.detail.id"},
                {"call": "timeline-view", "method": "highlightEvent", "args": ["event.detail.id"]},
                {"call": "detail-view", "method": "highlightEvent", "args": ["event.detail.id"]},
            ],
        }
    ],
}


def test_representative_definition_round_trips():
    definition = parse_app_definition(json.dumps(REPRESENTATIVE_DEFINITION))
    check("all three components parsed", len(definition.components) == 3)
    check("component tags round-trip", {c.tag for c in definition.components} == {"map-panel", "timeline-view", "detail-view"})
    check("two state slots parsed", len(definition.state) == 2)
    check("state slot default round-trips (None)", definition.state[0].default is None)
    check("state slot default round-trips ([])", definition.state[1].default == [])
    check("layout type is split", definition.layout.type == "split")
    check("layout has one variant", set(definition.layout.variants) == {"default"})
    tree = definition.layout.variants["default"]
    check("root node is hsplit", tree.type == "hsplit")
    check("root has two children", len(tree.children) == 2)
    check("first child is a pane with min_size", tree.children[0].type == "pane" and tree.children[0].min_size == 200)
    check("second child is a nested vsplit with two panes", tree.children[1].type == "vsplit" and len(tree.children[1].children) == 2)
    check("default_variant round-trips", definition.layout.default_variant == "default")
    check("one event-wiring entry parsed", len(definition.events) == 1)
    entry = definition.events[0]
    check("event name round-trips", entry.event == "marker-selected")
    check("emitter round-trips", entry.emitter == "map-panel")
    check("three actions parsed, fan-out preserved in order", len(entry.actions) == 3)
    check("first action is a state mutation", isinstance(entry.actions[0], StateMutationAction))
    check("state mutation target/source_expr round-trip", entry.actions[0].target == "selectedId" and entry.actions[0].source_expr == "event.detail.id")
    check("second/third actions are call actions to distinct targets", isinstance(entry.actions[1], CallAction) and isinstance(entry.actions[2], CallAction) and entry.actions[1].target != entry.actions[2].target)


def test_multi_chunk_like_repeated_parse_is_stable():
    """Not literally multi-chunk (that's a build_widget.py-style Html
    concept, not part of this DSL's own JSON format) -- confirms
    parsing the same representative definition twice is
    deterministic/side-effect-free."""
    a = parse_app_definition(json.dumps(REPRESENTATIVE_DEFINITION))
    b = parse_app_definition(json.dumps(REPRESENTATIVE_DEFINITION))
    check("parsing twice is deterministic", a == b)


def test_rejects_not_json():
    try:
        parse_app_definition("not json at all {{{")
        check("garbage JSON text rejected", False)
    except DslError as e:
        check("garbage JSON text rejected", "not valid JSON" in str(e))


def test_rejects_unknown_component_reference_in_layout():
    bad = json.loads(json.dumps(REPRESENTATIVE_DEFINITION))
    bad["layout"]["variants"]["default"]["children"][0]["widget"] = "nonexistent-widget"
    try:
        parse_app_definition(json.dumps(bad))
        check("unknown component reference in layout rejected", False)
    except DslError as e:
        check("unknown component reference in layout rejected", "nonexistent-widget" in str(e))


def test_rejects_unknown_state_slot_reference_in_action():
    bad = json.loads(json.dumps(REPRESENTATIVE_DEFINITION))
    bad["events"][0]["actions"][0]["set"] = "notARealSlot"
    try:
        parse_app_definition(json.dumps(bad))
        check("unknown state slot reference in action rejected", False)
    except DslError as e:
        check("unknown state slot reference in action rejected", "notARealSlot" in str(e))


def test_rejects_unknown_component_reference_in_call_action():
    bad = json.loads(json.dumps(REPRESENTATIVE_DEFINITION))
    bad["events"][0]["actions"][1]["call"] = "nonexistent-widget"
    try:
        parse_app_definition(json.dumps(bad))
        check("unknown component reference in call action rejected", False)
    except DslError as e:
        check("unknown component reference in call action rejected", "nonexistent-widget" in str(e))


def test_rejects_missing_required_key():
    bad = json.loads(json.dumps(REPRESENTATIVE_DEFINITION))
    del bad["components"][0]["source"]
    try:
        parse_app_definition(json.dumps(bad))
        check("missing required key rejected", False)
    except DslError as e:
        check("missing required key rejected", "source" in str(e))


def test_rejects_bad_type_discriminant():
    bad = json.loads(json.dumps(REPRESENTATIVE_DEFINITION))
    bad["layout"]["variants"]["default"]["type"] = "not-a-real-type"
    try:
        parse_app_definition(json.dumps(bad))
        check("bad layout node type discriminant rejected", False)
    except DslError as e:
        check("bad layout node type discriminant rejected", "not-a-real-type" in str(e))


def test_rejects_bad_layout_top_level_type():
    bad = json.loads(json.dumps(REPRESENTATIVE_DEFINITION))
    bad["layout"]["type"] = "not-a-real-layout-type"
    try:
        parse_app_definition(json.dumps(bad))
        check("bad top-level layout.type rejected", False)
    except DslError as e:
        check("bad top-level layout.type rejected", "not-a-real-layout-type" in str(e))


def test_rejects_default_variant_not_declared():
    bad = json.loads(json.dumps(REPRESENTATIVE_DEFINITION))
    bad["layout"]["default_variant"] = "no-such-variant"
    try:
        parse_app_definition(json.dumps(bad))
        check("undeclared default_variant rejected", False)
    except DslError as e:
        check("undeclared default_variant rejected", "no-such-variant" in str(e))


def test_rejects_duplicate_component_tag():
    bad = json.loads(json.dumps(REPRESENTATIVE_DEFINITION))
    bad["components"].append({"tag": "map-panel", "source": "other.ts"})
    try:
        parse_app_definition(json.dumps(bad))
        check("duplicate component tag rejected", False)
    except DslError as e:
        check("duplicate component tag rejected", "duplicate" in str(e).lower())


def test_windowed_layout_parses_at_schema_level():
    definition_dict = {
        "components": [{"tag": "map-panel", "source": "map-panel.ts"}],
        "layout": {
            "type": "windowed",
            "windows": [{"widget": "map-panel", "x": 0, "y": 0, "width": 400, "height": 300}],
        },
        "events": [],
        "state": [],
    }
    definition = parse_app_definition(json.dumps(definition_dict))
    check("windowed layout type parses", definition.layout.type == "windowed")
    check("windowed layout window entry round-trips", len(definition.layout.windows) == 1 and definition.layout.windows[0].widget == "map-panel")


def test_escape_hatch_handlers_parse_and_validate():
    definition_dict = {
        "components": [{"tag": "map-panel", "source": "map-panel.ts"}],
        "handlers": {"onWeird": {"module": "handlers.ts", "export": "handleWeird"}},
        "events": [
            {
                "event": "weird",
                "from": "map-panel",
                "actions": [{"call": "escape:onWeird", "method": "unused", "args": ["event.detail"]}],
            }
        ],
        "state": [],
    }
    definition = parse_app_definition(json.dumps(definition_dict))
    check("handler declared and round-trips", definition.handlers["onWeird"].export == "handleWeird")
    check("escape: call action target round-trips", definition.events[0].actions[0].target == "escape:onWeird")


def test_rejects_unknown_escape_handler():
    definition_dict = {
        "components": [{"tag": "map-panel", "source": "map-panel.ts"}],
        "events": [
            {
                "event": "weird",
                "from": "map-panel",
                "actions": [{"call": "escape:notDeclared", "method": "unused", "args": []}],
            }
        ],
        "state": [],
    }
    try:
        parse_app_definition(json.dumps(definition_dict))
        check("unknown escape-hatch handler reference rejected", False)
    except DslError as e:
        check("unknown escape-hatch handler reference rejected", "notDeclared" in str(e))


def test_component_class_name_override_parses():
    definition_dict = {
        "components": [
            {"tag": "map-panel", "source": "map-panel.ts"},
            {"tag": "timeline-view", "source": "timeline-view.ts", "class_name": "MyCustomTimelineClass"},
        ],
        "events": [],
        "state": [],
    }
    definition = parse_app_definition(json.dumps(definition_dict))
    check("component with no class_name defaults to None", definition.components[0].class_name is None)
    check("component with an explicit class_name round-trips it", definition.components[1].class_name == "MyCustomTimelineClass")


def test_component_class_name_rejects_bad_value():
    definition_dict = {
        "components": [{"tag": "map-panel", "source": "map-panel.ts", "class_name": ""}],
        "events": [],
        "state": [],
    }
    try:
        parse_app_definition(json.dumps(definition_dict))
        check("empty class_name rejected", False)
    except DslError as e:
        check("empty class_name rejected", "class_name" in str(e))


test_representative_definition_round_trips()
test_multi_chunk_like_repeated_parse_is_stable()
test_rejects_not_json()
test_rejects_unknown_component_reference_in_layout()
test_rejects_unknown_state_slot_reference_in_action()
test_rejects_unknown_component_reference_in_call_action()
test_rejects_missing_required_key()
test_rejects_bad_type_discriminant()
test_rejects_bad_layout_top_level_type()
test_rejects_default_variant_not_declared()
test_rejects_duplicate_component_tag()
test_windowed_layout_parses_at_schema_level()
test_escape_hatch_handlers_parse_and_validate()
test_rejects_unknown_escape_handler()
test_component_class_name_override_parses()
test_component_class_name_rejects_bad_value()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
