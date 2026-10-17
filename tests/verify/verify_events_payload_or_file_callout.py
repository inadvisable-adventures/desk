"""TODO 361b4f8: the inter-widget docs explain signal-only vs payload-carrying desk events and the
~1 KB file advice."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.shell import desk_mcp_server as mcp  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    AGENT_EVENTS_DOC_FILENAME, CURRENT_TAGS, SPLIT_DOC_CONTENT, _CUSTOM_WIDGETS_DOC, _NEW_FEATURES, _PORTING_DOC,
)

failures = 0


def check(name, ok):
    global failures
    print(("PASS" if ok else "FAIL") + ":", name)
    failures += 0 if ok else 1


HEADING = "### A signal, or the data itself"
check("subsection exists in the custom-widgets doc, once", _CUSTOM_WIDGETS_DOC.count(HEADING) == 1)
section = _CUSTOM_WIDGETS_DOC.split(HEADING, 1)[1].split("\n## ", 1)[0]
check("sits under the named-messages section, before the state section",
      _CUSTOM_WIDGETS_DOC.index("## Sending and receiving named messages") < _CUSTOM_WIDGETS_DOC.index(HEADING)
      < _CUSTOM_WIDGETS_DOC.index("## Shared, project-scoped state"))
check("bare-signal example with no payload", 'publish("report.updated")' in section and "I updated the file" in section)
check("data-instead-of-a-file example", "skips the file altogether" in section and "report.row_added" in section)
check("1 KB advice", "**1 KB**" in section and "prefer a file" in section)
check("late-subscriber caveat", "not kept for latecomers" in section)
check("the quoted hard limit equals the tool's", f"{mcp.MAX_EVENT_PAYLOAD_BYTES // 1024} KiB" in section)
check("section names both agent tools", "desk_raise_event" in section and "desk_wait_for_event" in section)
porting = " ".join(_PORTING_DOC.split())  # the bullet wraps across lines
check("porting doc points to the callout", "A signal, or the data itself" in porting and "about 1 KB" in porting)
check("agent-events doc points to the callout", "A signal, or the data itself" in SPLIT_DOC_CONTENT[AGENT_EVENTS_DOC_FILENAME])
tag = next((t for t in CURRENT_TAGS if "bare signal or payload" in t), None)
check("tag has a changelog entry mentioning the section", tag in _NEW_FEATURES and "A signal, or the" in _NEW_FEATURES[tag])

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
