# TODO aa0ce76 follow-up: the tempui docs tell agents where Desk's own log is.
import sys

sys.path.insert(0, "src")

from desk.temp_ui import CURRENT_TAGS, DOC_TEMPLATE, _NEW_FEATURES  # noqa: E402

TAG = "Desk log file at .desk_temp/logs/desk.log #236455"
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


flat = " ".join(DOC_TEMPLATE.split())
check("main doc has a section on Desk's own log", "## Desk's own log" in DOC_TEMPLATE)
check("main doc names the path", ".desk_temp/logs/desk.log" in flat)
check("main doc says agents may read it", "you're welcome to read it" in flat)
check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", TAG in CURRENT_TAGS and TAG in _NEW_FEATURES)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
