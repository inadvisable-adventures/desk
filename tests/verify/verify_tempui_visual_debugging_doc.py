# TODO b9c7828: tempui-custom-widgets.md's "Debugging a widget's own
# rendering/geometry visually" section, plus its changelog tag/entry.
import sys

sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    _CUSTOM_WIDGETS_DOC,
    _NEW_FEATURES,
    CURRENT_TAGS,
    CURRENT_TAG_SET,
)

TAG = "visual debugging of widget geometry guidance #733899"
HEADING = "## Debugging a widget's own rendering/geometry visually"
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
check("section heading present exactly once", _CUSTOM_WIDGETS_DOC.count(HEADING) == 1)
check("sits after 'Authoring from real source' and before 'Reusable UI components'",
      _CUSTOM_WIDGETS_DOC.index("## Authoring from real source") < _CUSTOM_WIDGETS_DOC.index(HEADING)
      < _CUSTOM_WIDGETS_DOC.index("## Reusable UI components"))
check("names the build marker", "BUILD_MARKER" in flat and "is this actually the new code" in flat)
check("names the real-outcome debug layer", "real outcomes" in flat and "isPointInPath" in flat)
check("names ground-truth markers via the same function", "same function you are verifying" in flat or "very projection function" in flat)
check("tells the agent to close the loop with the screenshot tools",
      "desk_screenshot_widget" in flat and "desk_reveal_widget" in flat and "max_width" in flat)
check("honestly notes there is no synthesized-input tool", "no way for an agent to synthesize" in flat)
check("includes the isPointInPath worked example", "identity transform" in flat and "devicePixelRatio" in flat)
check("tag is in CURRENT_TAGS", TAG in CURRENT_TAGS and TAG in CURRENT_TAG_SET)
check("tag has a _NEW_FEATURES entry", TAG in _NEW_FEATURES and "geometry visually" in _NEW_FEATURES[TAG])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
