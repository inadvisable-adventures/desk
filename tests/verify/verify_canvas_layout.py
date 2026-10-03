"""Verifies TODO `669b690`'s pure arrangement algorithms
(desk.canvas_layout)."""

import sys

sys.path.insert(0, "src")

from desk.canvas_layout import (  # noqa: E402
    GAP,
    nudge_apart,
    organize_by_kind,
    restorable,
    snapshot_moves,
    tile,
)

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


def rect(id, x, y, w=100, h=80, kind="k", locked=False):
    return {"id": id, "kind": kind, "x": x, "y": y, "w": w, "h": h, "locked": locked}


def apply(rects, moves):
    return [dict(r, x=moves[r["id"]][0], y=moves[r["id"]][1]) if r["id"] in moves else r for r in rects]


def overlaps(rects):
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            if min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]) > 0 and min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]) > 0:
                return True
    return False


def test_nudge_resolves_overlaps_and_leaves_others():
    rects = [rect("a", 0, 0), rect("b", 50, 20), rect("c", 60, 30), rect("far", 5000, 5000)]
    check("sanity: they overlap to begin with", overlaps(rects))
    moves = nudge_apart(rects)
    check("no overlaps afterwards", not overlaps(apply(rects, moves)))
    check("a widget overlapping nothing isn't moved", "far" not in moves)
    check("sizes are untouched (positions only)", all(len(v) == 2 for v in moves.values()))
    check("a non-overlapping layout needs no moves", nudge_apart([rect("a", 0, 0), rect("b", 500, 0)]) == {})


def test_nudge_respects_locked():
    rects = [rect("fixed", 0, 0, locked=True), rect("free", 40, 10)]
    moves = nudge_apart(rects)
    check("a locked widget never moves", "fixed" not in moves)
    check("the other takes the whole push and clears it", "free" in moves and not overlaps(apply(rects, moves)))
    both = [rect("l1", 0, 0, locked=True), rect("l2", 10, 10, locked=True)]
    check("two locked overlapping widgets are left alone (and it terminates)", nudge_apart(both) == {})
    stacked = [rect("a", 0, 0), rect("b", 0, 0), rect("c", 0, 0), rect("d", 0, 0)]
    check("even four identically placed widgets get separated", not overlaps(apply(stacked, nudge_apart(stacked))))


def test_tile():
    rects = [rect(str(i), i * 10, i * 5, w=100 + i, h=80) for i in range(5)] + [rect("lk", 900, 900, locked=True)]
    moves = tile(rects)
    check("locked widgets are not tiled", "lk" not in moves and len(moves) == 5)
    placed = apply(rects, moves)
    check("tiling leaves no overlaps", not overlaps(placed))
    xs = sorted({round(moves[str(i)][0]) for i in range(5)})
    check("a 5-widget grid has ceil(sqrt(5)) = 3 columns", len(xs) == 3)
    check("anchored at the bounding box's top-left", min(m[0] for m in moves.values()) == 0 and min(m[1] for m in moves.values()) == 0)
    check("empty input is fine", tile([]) == {})


def test_organize_by_kind():
    rects = [rect("p1", 0, 0, kind="python"), rect("h1", 200, 0, kind="html"), rect("p2", 400, 0, kind="python"), rect("h2", 600, 0, kind="html")]
    moves = organize_by_kind(rects)
    check("no overlaps", not overlaps(apply(rects, moves)))
    check("same-kind widgets share a row", moves["p1"][1] == moves["p2"][1] and moves["h1"][1] == moves["h2"][1])
    check("different kinds are on different rows, first-seen kind first", moves["p1"][1] < moves["h1"][1])
    check("a row keeps placement order with a gap", moves["p2"][0] == moves["p1"][0] + 100 + GAP)
    check("empty input is fine", organize_by_kind([]) == {})
    wide = [rect(str(i), i * 10, 0, w=1000, kind="k") for i in range(5)]
    placed = apply(wide, organize_by_kind(wide))
    check("a long group wraps instead of running off forever", len({r["y"] for r in placed}) > 1 and not overlaps(placed))


def test_undo_snapshot_semantics():
    before = [rect("a", 0, 0), rect("b", 50, 20), rect("c", 9000, 0)]
    moves = nudge_apart(before)
    snap = snapshot_moves(before, moves)
    originals = {r["id"]: (r["x"], r["y"]) for r in before}
    check("the snapshot holds exactly what moved, at its old place", set(snap) == set(moves) and all(snap[i] == originals[i] for i in snap))
    check("it excludes widgets that didn't move", "c" not in snap)
    # Between arrange and undo: 'b' is closed, 'new' is opened.
    present = {"a", "c", "new"}
    restored = restorable(snap, present)
    check("a widget closed since is skipped", "b" not in restored)
    check("a widget opened since is never touched", "new" not in restored)
    check("surviving widgets are restored", set(restored) == (set(snap) & present))
    check("a no-op arrangement snapshots nothing", snapshot_moves(before, {}) == {})


test_nudge_resolves_overlaps_and_leaves_others()
test_nudge_respects_locked()
test_tile()
test_organize_by_kind()
test_undo_snapshot_semantics()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
