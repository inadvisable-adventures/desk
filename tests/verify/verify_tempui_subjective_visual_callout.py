# TODO e501d8a: tempui-custom-widgets.md callout naming a human's
# subjective visual judgment as a signal to propose a DefineWidget.
import sys

sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    _CUSTOM_WIDGETS_DOC,
    _NEW_FEATURES,
    CURRENT_TAGS,
    CURRENT_TAG_SET,
)

TAG = "widget for subjective visual tasks guidance #588265"
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


flat = " ".join(_CUSTOM_WIDGETS_DOC.split())
check("names subjective visual judgment", "subjective visual judgment" in flat)
check("gives crop/select, placement/composite, heuristic examples",
      "cropping or selecting a region in an image" in flat and "placement/composite/layout" in flat
      and "fixed heuristic" in flat)
check("says to propose a widget even if not asked", "even when their request did not ask for one" in flat)
check("says heuristic seeds a default", "seed a sensible default" in flat)
check("says the widget only selects, a script does the work", "writing the confirmed rectangles" in flat and "ordinary script" in flat)
check("callout sits before the line-format list",
      _CUSTOM_WIDGETS_DOC.index("When to propose a widget yourself") < _CUSTOM_WIDGETS_DOC.index("Lines are **tab**-separated"))
check("tag is in CURRENT_TAGS", TAG in CURRENT_TAGS and TAG in CURRENT_TAG_SET)
check("tag has a _NEW_FEATURES entry", TAG in _NEW_FEATURES and "subjective visual judgment" in _NEW_FEATURES[TAG])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
