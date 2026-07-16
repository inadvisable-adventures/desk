import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

from desk.shell import current_context  # noqa: E402

app = QApplication(sys.argv)

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

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


def load_widget_module():
    spec = importlib.util.spec_from_file_location(
        "transform_manager_widget_test", REPO_ROOT / "widgets/transform_manager/widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load_widget_module()


def write_manifest(directory: Path, name: str, manifest: dict) -> Path:
    d = directory / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "transform.json").write_text(json.dumps(manifest))
    return d


def col_text(table, row, column):
    item = table.item(row, column)
    return item.text() if item is not None else None


def find_row_by_name(table, name):
    for row in range(table.rowCount()):
        if col_text(table, row, 0) == name:
            return row
    return None


def test_populates_table_from_real_transforms():
    with tempfile.TemporaryDirectory() as d:
        desk_dir = Path(d)
        desk_temp_dir = desk_dir / ".desk_temp" / "transforms"
        project_dir = desk_dir / "desk_transforms"
        write_manifest(
            desk_temp_dir,
            "local_one",
            {
                "name": "Local One",
                "kind": "javascript",
                "entry": "transform.js",
                "input_type": "foo",
                "output_type": "bar",
                "has_config": True,
            },
        )
        write_manifest(
            project_dir,
            "proj_one",
            {
                "name": "Project One",
                "kind": "python",
                "entry": "transform.py",
                "input_type": "a",
                "output_type": "b",
                "has_identity": True,
            },
        )

        with patch.object(current_context, "get_current_desk_directory", return_value=desk_dir):
            w = mod.build()

        local_row = find_row_by_name(w._table, "Local One")
        check("a local (.desk_temp) transform is listed", local_row is not None)
        check(
            "local row's columns are correct",
            col_text(w._table, local_row, 1) == "foo"
            and col_text(w._table, local_row, 2) == "bar"
            and col_text(w._table, local_row, 3) == "javascript"
            and col_text(w._table, local_row, 4) == "Yes"
            and col_text(w._table, local_row, 5) == "No"
            and col_text(w._table, local_row, 6) == "Local (.desk_temp)",
        )
        check(
            "a local transform's row has a Promote button",
            isinstance(w._table.cellWidget(local_row, mod.PROMOTE_COLUMN), QPushButton),
        )

        project_row = find_row_by_name(w._table, "Project One")
        check("a project-level transform is listed", project_row is not None)
        check(
            "project row's columns are correct",
            col_text(w._table, project_row, 3) == "python"
            and col_text(w._table, project_row, 5) == "Yes"
            and col_text(w._table, project_row, 6) == "Project",
        )
        check(
            "a project-level transform's row has no Promote button",
            w._table.cellWidget(project_row, mod.PROMOTE_COLUMN) is None,
        )
        w.deleteLater()


def test_discovery_error_shows_as_an_error_row():
    with tempfile.TemporaryDirectory() as d:
        desk_dir = Path(d)
        desk_temp_dir = desk_dir / ".desk_temp" / "transforms"
        write_manifest(
            desk_temp_dir,
            "broken_python",
            {"name": "Broken", "kind": "python", "entry": "transform.py", "input_type": "a", "output_type": "b"},
        )

        with patch.object(current_context, "get_current_desk_directory", return_value=desk_dir):
            w = mod.build()

        check("nothing was discovered as a real transform", w._table.rowCount() == 1)
        error_text = col_text(w._table, 0, 0)
        check(
            "the Python-under-.desk_temp rejection shows as a visible error row",
            error_text is not None and "broken_python" in error_text and "Python" in error_text,
        )
        w.deleteLater()


def test_promote_button_moves_the_real_directory_and_refreshes():
    with tempfile.TemporaryDirectory() as d:
        desk_dir = Path(d)
        desk_temp_dir = desk_dir / ".desk_temp" / "transforms"
        project_dir = desk_dir / "desk_transforms"
        write_manifest(
            desk_temp_dir,
            "promote_me",
            {"name": "Promote Me", "kind": "javascript", "entry": "transform.js", "input_type": "a", "output_type": "b"},
        )
        (desk_temp_dir / "promote_me" / "transform.js").write_text("// stub")

        with patch.object(current_context, "get_current_desk_directory", return_value=desk_dir):
            w = mod.build()
            row = find_row_by_name(w._table, "Promote Me")
            button = w._table.cellWidget(row, mod.PROMOTE_COLUMN)

            with patch.object(current_context, "get_popup_opener", return_value=lambda *a: "Promote"):
                button.click()

            check(
                "confirming Promote actually moves the directory on disk",
                not (desk_temp_dir / "promote_me").exists() and (project_dir / "promote_me").is_dir(),
            )
            check(
                "after promoting, the row now shows as Project-located with no Promote button",
                find_row_by_name(w._table, "Promote Me") is not None
                and col_text(w._table, find_row_by_name(w._table, "Promote Me"), 6) == "Project"
                and w._table.cellWidget(find_row_by_name(w._table, "Promote Me"), mod.PROMOTE_COLUMN) is None,
            )
            w.deleteLater()


def test_declining_promote_leaves_everything_untouched():
    with tempfile.TemporaryDirectory() as d:
        desk_dir = Path(d)
        desk_temp_dir = desk_dir / ".desk_temp" / "transforms"
        write_manifest(
            desk_temp_dir,
            "stay_put",
            {"name": "Stay Put", "kind": "javascript", "entry": "transform.js", "input_type": "a", "output_type": "b"},
        )
        (desk_temp_dir / "stay_put" / "transform.js").write_text("// stub")

        with patch.object(current_context, "get_current_desk_directory", return_value=desk_dir):
            w = mod.build()
            row = find_row_by_name(w._table, "Stay Put")
            button = w._table.cellWidget(row, mod.PROMOTE_COLUMN)

            with patch.object(current_context, "get_popup_opener", return_value=lambda *a: "Cancel"):
                button.click()

            check("declining the confirmation leaves the .desk_temp source untouched", (desk_temp_dir / "stay_put").is_dir())
            w.deleteLater()


def test_refresh_button_picks_up_new_transforms():
    with tempfile.TemporaryDirectory() as d:
        desk_dir = Path(d)
        desk_temp_dir = desk_dir / ".desk_temp" / "transforms"

        with patch.object(current_context, "get_current_desk_directory", return_value=desk_dir):
            w = mod.build()
            check("nothing discovered yet", w._table.rowCount() == 0)

            write_manifest(
                desk_temp_dir,
                "new_one",
                {"name": "New One", "kind": "javascript", "entry": "transform.js", "input_type": "a", "output_type": "b"},
            )
            w._refresh_button.click()
            check("Refresh picks up a transform added after the widget was built", find_row_by_name(w._table, "New One") is not None)
            w.deleteLater()


test_populates_table_from_real_transforms()
test_discovery_error_shows_as_an_error_row()
test_promote_button_moves_the_real_directory_and_refreshes()
test_declining_promote_leaves_everything_untouched()
test_refresh_button_picks_up_new_transforms()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
