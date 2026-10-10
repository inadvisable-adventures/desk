"""TODO 66aa766: `current_context`'s hook aliases must match the real
`DeskWindow` methods bound to them (see plans/hook-signature-conformance.md
and investigations/hook-signature-drift.md)."""
import inspect
import os
import re
import sys
import typing
from collections.abc import Callable
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

import desk.shell.widget_frame  # noqa: E402,F401
from desk.shell import current_context  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def _callable_args(hint):
    """The positional parameter types of a `Callable[[...], R] | None` hint."""
    for part in typing.get_args(hint) or (hint,):
        if typing.get_origin(part) is Callable or typing.get_origin(part) is getattr(__import__("collections.abc").abc, "Callable"):
            return list(typing.get_args(part)[0])
    return None


# 1. Every `set_X(self.method)` binding in DeskWindow: the alias' positional
#    parameters must be accepted, in order and with equal types, by the method.
from desk.shell.hud import HudController  # noqa: E402  (a TYPE_CHECKING-only name in current_context)

module_hints = typing.get_type_hints(current_context, localns={"HudController": HudController})
source = Path("src/desk/shell/window.py").read_text(encoding="utf-8")
bindings = re.findall(r"current_context\.set_(\w+)\(self\.(\w+)\)", source)
check("found the hook bindings", len(bindings) > 20, str(len(bindings)))
for hook, method_name in bindings:
    method = getattr(DeskWindow, method_name, None)
    alias = module_hints.get(f"_{hook}")
    if method is None or alias is None:
        continue  # not a plain method (an object, e.g. the event mediator)
    alias_args = _callable_args(alias)
    if alias_args is None:
        continue  # a Protocol-typed hook: checked in section 2
    params = [p for p in inspect.signature(method).parameters.values() if p.name != "self"]
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    required = [p for p in params if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    hints = typing.get_type_hints(method)
    ok = len(alias_args) <= len(positional) and len(alias_args) >= len(required)
    problems = []
    if not ok:
        problems.append(f"alias takes {len(alias_args)} positional, method takes {len(positional)} ({len(required)} required)")
    for i, (a, p) in enumerate(zip(alias_args, positional)):
        if p.name in hints and hints[p.name] != a:
            problems.append(f"position {i} ({p.name}): alias {a} vs method {hints[p.name]}")
    check(f"{hook} alias matches DeskWindow.{method_name}", not problems, "; ".join(problems))

# 2. The centered opener's Protocol is exactly the real method's signature.
real = inspect.signature(DeskWindow.open_widget_content_centered)
proto = inspect.signature(current_context.CenteredWidgetOpener.__call__)
real_params = [p for n, p in real.parameters.items() if n != "self"]
proto_params = [p for n, p in proto.parameters.items() if n != "self"]
shape = lambda ps: [(p.name, p.kind, p.default) for p in ps]
check("CenteredWidgetOpener signature equals open_widget_content_centered's", shape(real_params) == shape(proto_params), f"{shape(real_params)} vs {shape(proto_params)}")
real_hints = typing.get_type_hints(DeskWindow.open_widget_content_centered)
proto_hints = typing.get_type_hints(current_context.CenteredWidgetOpener.__call__)
check("... including annotations", real_hints == proto_hints)

# 3. Call the REAL method the way a widget does (positionally, as the Claude
#    (Desk) widget does), not through a hand-written fake of the alias.
from desk.widgets import WidgetInfo  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402


class _Stand_In:
    def __init__(self):
        self._widgets = {
            "markdown": WidgetInfo(
                id="markdown", path=Path("."), kind="python", name="Markdown", entry="widget.py",
                capabilities=[], default_size=(400, 300),
            )
        }
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self.calls = []

    def open_widget_content(self, widget_id, pos=None, size=None, instance_id=None, path=None):
        self.calls.append({"widget_id": widget_id, "size": size, "instance_id": instance_id, "path": path})
        return "content"


_Stand_In.open_widget_content_centered = DeskWindow.open_widget_content_centered
win = _Stand_In()
opener: current_context.CenteredWidgetOpener = win.open_widget_content_centered
result = opener("markdown", Path("turn.md"))
check("positional (widget_id, path) delivers the Path as path", result == "content" and win.calls[-1]["path"] == Path("turn.md"))
check("... and leaves size at the widget default", win.calls[-1]["size"] == (400, 300) and win.calls[-1]["instance_id"] is None)
opener("markdown")
check("path defaults to None", win.calls[-1]["path"] is None)
try:
    opener("markdown", Path("x"), (10, 10))
    check("size cannot be passed positionally", False)
except TypeError:
    check("size cannot be passed positionally", True)
opener("markdown", size=(10, 10), instance_id="i1")
check("size/instance_id by keyword", win.calls[-1]["size"] == (10, 10) and win.calls[-1]["instance_id"] == "i1")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
