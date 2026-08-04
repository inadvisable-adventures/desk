# Note: the tests that place a real ClaudeWidget and spawn a real
# `claude` CLI process (a live Claude API dependency: real network
# calls, real API cost) were split out to
# tests/verify/disabled_verify_discuss_parking_lot_item_claude_api.py
# and disabled there (TODO 9bc522b). The tests remaining here are pure
# parsing/doc-content checks -- no live API involved.
import sys

sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    DISCUSS_PARKING_LOT_ITEM_KEYWORD,
    DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    detect_temp_ui_kind,
    parse_discuss_parking_lot_item,
)


# ---------- pure parsing/doc-content checks ----------


def test_detect_and_parse():
    # TODO 624ff3a: the second line is now `Line <N>` (a reference into
    # PARKINGLOT.md), not the item's own embedded text -- parse returns
    # (label, line_number), not (label, full_body_text).
    text = "DiscussParkingLotItem A way to end a session\nLine 42"
    assert detect_temp_ui_kind(text) == "discuss_parking_lot_item"
    parsed = parse_discuss_parking_lot_item(text)
    assert parsed == ("A way to end a session", 42)
    assert parse_discuss_parking_lot_item("Scratch hi\nbody") is None
    assert parse_discuss_parking_lot_item("DiscussParkingLotItem A way to end a session\nnot a line ref") is None
    print("detect_temp_ui_kind/parse_discuss_parking_lot_item: PASS")


def test_doc_version_and_split_file():
    assert TEMPUI_DOC_VERSION >= 5
    content = SPLIT_DOC_CONTENT[DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME]
    assert DISCUSS_PARKING_LOT_ITEM_KEYWORD in content
    assert "PARKINGLOT.md" in content
    print("TEMPUI_DOC_VERSION bumped + tempui-discuss-parking-lot-item.md content present: PASS")


test_detect_and_parse()
test_doc_version_and_split_file()
print("ALL PASS")
