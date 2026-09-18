import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "todo_item_ids.py"

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


FIXTURE = """1. First item description text, long enough to hash well.
2. Second item description text, long enough to hash well.
3. Third item description text, long enough to hash well.

See items 1/2 for the slash-separated case.

<!-- Item format:
1. a literal example line, not a real item
2. another literal example line, not a real item
-->

Also mentioned in TODO item 3 previously (should not double-prefix).

Covers items 1-3 in one go (en-dash range: items 1–3 too).
"""


def run_convert(fixture_text):
    with tempfile.TemporaryDirectory() as d:
        todo_path = Path(d) / "TODO.md"
        todo_path.write_text(fixture_text)
        result = subprocess.run(
            ["/usr/bin/env", "python3", str(SCRIPT_PATH), "convert", str(todo_path)],
            capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        )
        return result, todo_path.read_text() if result.returncode == 0 else None


def test_real_items_convert_and_html_comment_literal_lines_are_untouched():
    result, converted = run_convert(FIXTURE)
    check("convert exits 0", result.returncode == 0, )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        return
    lines = converted.splitlines()
    check(
        "the three real top-level items were each converted to a hash id (not left as N.)",
        not lines[0].split(".", 1)[0].isdigit()
        and not lines[1].split(".", 1)[0].isdigit()
        and not lines[2].split(".", 1)[0].isdigit(),
    )
    check(
        "the HTML comment's own literal '1. ...' example line is untouched",
        "1. a literal example line, not a real item" in converted,
    )
    check(
        "the HTML comment's own literal '2. ...' example line is untouched",
        "2. another literal example line, not a real item" in converted,
    )
    return converted


def test_slash_separated_plural_reference_converts():
    _, converted = run_convert(FIXTURE)
    check(
        "'items 1/2' converts to two slash-joined TODO references",
        "See TODO " in converted and "/TODO " in converted.split("See TODO ", 1)[1].split(" for", 1)[0],
    )
    check("no bare 'items 1/2' left behind", "items 1/2" not in converted)


def test_todo_item_n_does_not_double_prefix():
    _, converted = run_convert(FIXTURE)
    check("'TODO item 3' converted without double-prefixing", "TODO TODO " not in converted)
    check("no bare 'TODO item 3' left behind", "TODO item 3" not in converted)
    check("a real 'TODO <id>' reference replaced it", "Also mentioned in TODO " in converted)


def test_en_dash_range_converts():
    _, converted = run_convert(FIXTURE)
    check("no bare 'items 1-3' left behind", "items 1-3" not in converted)
    check("no bare en-dash 'items 1–3' left behind", "items 1–3" not in converted)
    check(
        "the hyphen range expanded to three slash-joined TODO references",
        "Covers TODO " in converted and converted.count("TODO ", converted.index("Covers TODO ")) >= 3,
    )


def test_number_to_id_mapping_is_printed():
    result, _ = run_convert(FIXTURE)
    check("prints a 1 -> <id> mapping line", any(line.startswith("1 -> ") for line in result.stdout.splitlines()))
    check("prints a 2 -> <id> mapping line", any(line.startswith("2 -> ") for line in result.stdout.splitlines()))
    check("prints a 3 -> <id> mapping line", any(line.startswith("3 -> ") for line in result.stdout.splitlines()))


test_real_items_convert_and_html_comment_literal_lines_are_untouched()
test_slash_separated_plural_reference_converts()
test_todo_item_n_does_not_double_prefix()
test_en_dash_range_converts()
test_number_to_id_mapping_is_printed()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
