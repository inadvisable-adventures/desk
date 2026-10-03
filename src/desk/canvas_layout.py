"""Pure canvas-arrangement algorithms for the Minimap widget (TODO 669b690).

Rects are dicts {"id", "kind", "x", "y", "w", "h", "locked"} in placement
order. Every function returns {id: (x, y)} for only the widgets that should
move -- sizes never change. See plans/minimap-widget.md.
"""
import math

GAP = 24.0
GROUP_GAP = 64.0
MAX_ROW_WIDTH = 2400.0
NUDGE_PADDING = 8.0
NUDGE_MAX_ITERATIONS = 400


def _anchor(rects: list[dict]) -> tuple[float, float]:
    return min(r["x"] for r in rects), min(r["y"] for r in rects)


def _movable(rects: list[dict]) -> list[dict]:
    return [r for r in rects if not r.get("locked")]


def tile(rects: list[dict]) -> dict[str, tuple[float, float]]:
    """Row-major grid of the unlocked widgets, anchored at the top-left of
    everything's bounding box."""
    movable = _movable(rects)
    if not movable:
        return {}
    ax, ay = _anchor(rects)
    columns = max(1, math.ceil(math.sqrt(len(movable))))
    cell_w = max(r["w"] for r in movable) + GAP
    cell_h = max(r["h"] for r in movable) + GAP
    return {r["id"]: (ax + (i % columns) * cell_w, ay + (i // columns) * cell_h) for i, r in enumerate(movable)}


def organize_by_kind(rects: list[dict]) -> dict[str, tuple[float, float]]:
    """Groups the unlocked widgets by kind (first-appearance order); each
    group is wrapped rows, groups stacked top to bottom."""
    movable = _movable(rects)
    if not movable:
        return {}
    ax, ay = _anchor(rects)
    groups: dict[str, list[dict]] = {}
    for r in movable:
        groups.setdefault(r.get("kind", ""), []).append(r)
    out: dict[str, tuple[float, float]] = {}
    y = ay
    for members in groups.values():
        x, row_h = ax, 0.0
        for r in members:
            if x > ax and x + r["w"] - ax > MAX_ROW_WIDTH:
                x, y, row_h = ax, y + row_h + GAP, 0.0
            out[r["id"]] = (x, y)
            x += r["w"] + GAP
            row_h = max(row_h, r["h"])
        y += row_h + GROUP_GAP
    return out


def _overlap(a: dict, b: dict) -> tuple[float, float] | None:
    ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return (ox, oy) if ox > 0 and oy > 0 else None


def nudge_apart(rects: list[dict]) -> dict[str, tuple[float, float]]:
    """Separates overlapping widgets along each pair's minimum-translation
    axis, half each way, until none overlap. Locked widgets never move (the
    other one takes the whole push; two locked ones stay). Widgets that
    overlap nothing aren't touched."""
    work = {r["id"]: dict(r) for r in rects}
    original = {r["id"]: (r["x"], r["y"]) for r in rects}
    items = list(work.values())
    for _ in range(NUDGE_MAX_ITERATIONS):
        moved = False
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                overlap = _overlap(a, b)
                if overlap is None or (a.get("locked") and b.get("locked")):
                    continue
                ox, oy = overlap
                if ox <= oy:
                    push = (ox + NUDGE_PADDING) * (1 if a["x"] + a["w"] / 2 <= b["x"] + b["w"] / 2 else -1)
                    axis = "x"
                else:
                    push = (oy + NUDGE_PADDING) * (1 if a["y"] + a["h"] / 2 <= b["y"] + b["h"] / 2 else -1)
                    axis = "y"
                if a.get("locked"):
                    b[axis] += push
                elif b.get("locked"):
                    a[axis] -= push
                else:
                    a[axis] -= push / 2
                    b[axis] += push / 2
                moved = True
        if not moved:
            break
    return {i: (w["x"], w["y"]) for i, w in work.items() if (w["x"], w["y"]) != original[i]}


ARRANGEMENTS = {"tile": tile, "organize": organize_by_kind, "nudge": nudge_apart}


def snapshot_moves(rects: list[dict], moves: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    """The positions (before the move) of exactly the widgets that move."""
    return {r["id"]: (r["x"], r["y"]) for r in rects if r["id"] in moves and moves[r["id"]] != (r["x"], r["y"])}


def restorable(snapshot: dict[str, tuple[float, float]], present_ids: set[str]) -> dict[str, tuple[float, float]]:
    """The part of an undo snapshot that can still be applied: widgets closed
    since are skipped; widgets opened since were never in it, so they stay
    exactly where they landed."""
    return {i: pos for i, pos in snapshot.items() if i in present_ids}
