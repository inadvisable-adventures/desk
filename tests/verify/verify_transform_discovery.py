import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.transforms import discover_transforms, discover_transforms_with_errors  # noqa: E402

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


def write_manifest(directory: Path, name: str, manifest: dict) -> None:
    d = directory / name
    d.mkdir(parents=True, exist_ok=True)
    import json

    (d / "transform.json").write_text(json.dumps(manifest))


VALID_JS_MANIFEST = {
    "name": "Test Transform",
    "kind": "javascript",
    "entry": "transform.js",
    "input_type": "foo",
    "output_type": "bar",
}


def test_valid_manifest_discovered():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        write_manifest(project_dir, "my_transform", VALID_JS_MANIFEST)
        transforms = discover_transforms(None, project_dir)
        check("a valid transform.json is discovered", "my_transform" in transforms)
        info = transforms["my_transform"]
        check(
            "TransformInfo fields are parsed correctly",
            info.kind == "javascript"
            and info.entry == "transform.js"
            and info.input_type == "foo"
            and info.output_type == "bar"
            and info.has_config is False
            and info.has_identity is False
            and info.location == "project",
        )


def test_missing_manifest_key_is_an_error_not_a_crash():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        write_manifest(project_dir, "broken", {"kind": "javascript", "entry": "transform.js"})
        transforms, errors = discover_transforms_with_errors(None, project_dir)
        check("a transform missing a required key isn't discovered", "broken" not in transforms)
        check("...but is recorded in the errors dict", "broken" in errors)


def test_invalid_kind_is_an_error():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        write_manifest(project_dir, "weird", {**VALID_JS_MANIFEST, "kind": "rust"})
        transforms, errors = discover_transforms_with_errors(None, project_dir)
        check("an invalid kind isn't discovered", "weird" not in transforms)
        check("...and is recorded in the errors dict", "weird" in errors)


def test_python_rejected_under_desk_temp():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d) / ".desk_temp" / "transforms"
        write_manifest(desk_temp_dir, "py_thing", {**VALID_JS_MANIFEST, "kind": "python", "entry": "transform.py"})
        transforms, errors = discover_transforms_with_errors(desk_temp_dir, None)
        check("a Python transform under .desk_temp isn't discovered", "py_thing" not in transforms)
        check(
            "...and the error explains why",
            "py_thing" in errors and "Python" in errors["py_thing"],
        )


def test_python_allowed_at_project_level():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        write_manifest(project_dir, "py_thing", {**VALID_JS_MANIFEST, "kind": "python", "entry": "transform.py"})
        transforms = discover_transforms(None, project_dir)
        check("a Python transform at project level is discovered fine", "py_thing" in transforms)


def test_project_wins_id_collision():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d) / ".desk_temp" / "transforms"
        project_dir = Path(d) / "desk_transforms"
        write_manifest(desk_temp_dir, "shared_id", {**VALID_JS_MANIFEST, "name": "Local copy"})
        write_manifest(project_dir, "shared_id", {**VALID_JS_MANIFEST, "name": "Promoted copy"})
        transforms = discover_transforms(desk_temp_dir, project_dir)
        check(
            "project-level wins a transform_id collision over .desk_temp",
            transforms["shared_id"].name == "Promoted copy" and transforms["shared_id"].location == "project",
        )


def test_nonexistent_directories_are_harmless():
    with tempfile.TemporaryDirectory() as d:
        transforms, errors = discover_transforms_with_errors(Path(d) / "nope", Path(d) / "also_nope")
        check("nonexistent directories produce no transforms and no errors", transforms == {} and errors == {})


def test_none_directories_are_harmless():
    transforms, errors = discover_transforms_with_errors(None, None)
    check("None directories produce no transforms and no errors", transforms == {} and errors == {})


test_valid_manifest_discovered()
test_missing_manifest_key_is_an_error_not_a_crash()
test_invalid_kind_is_an_error()
test_python_rejected_under_desk_temp()
test_python_allowed_at_project_level()
test_project_wins_id_collision()
test_nonexistent_directories_are_harmless()
test_none_directories_are_harmless()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
