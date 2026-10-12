"""TODO 1f74c27: the shared contracts in desk.widget_logs (store, clock,
recording event payloads)."""
import sys
import threading
from datetime import datetime, timezone

from desk import widget_logs as wl

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("PASS" if ok else "FAIL"), label)
    failures += 0 if ok else 1


store = wl.WidgetLogStore()
check("unknown log queries empty", store.query("nope") == [])
store.append("a-1", [(300, "c"), (100, "a"), (200, "b"), (200, "b2")])
check("sorted, stable on equal t", [e.text for e in store.query("a-1")] == ["a", "b", "b2", "c"])
check("range inclusive both ends", [e.text for e in store.query("a-1", 100, 200)] == ["a", "b", "b2"])
check("start only", [e.text for e in store.query("a-1", start_ms=201)] == ["c"])
check("limit takes first", [e.text for e in store.query("a-1", limit=2)] == ["a", "b"])
check("newest_first limit", [e.text for e in store.query("a-1", limit=2, newest_first=True)] == ["c", "b2"])
before = wl.now_ms()
store.append("a-1", [(None, "stamped")])
after = wl.now_ms()
last = store.query("a-1", limit=1, newest_first=True)[0]
check("None t stamped with arrival time", last.text == "stamped" and before <= last.t <= after)
store.append("long", [(1, "x" * (wl.MAX_ENTRY_TEXT_CHARS + 50))])
check("text cap", len(store.query("long")[0].text) == wl.MAX_ENTRY_TEXT_CHARS)

wl.MAX_ENTRIES_PER_LOG = 5
store.append("ring", [(i, str(i)) for i in range(10)])
check("ring drops oldest", [e.t for e in store.query("ring")] == [5, 6, 7, 8, 9])
wl.MAX_ENTRIES_PER_LOG = 10_000

summary = {s.name: s for s in store.list_logs()}
check("list_logs summary", summary["ring"].count == 5 and summary["ring"].first_t == 5 and summary["ring"].last_t == 9)
try:
    store.append("", [(1, "x")])
    check("empty name rejected", False)
except ValueError:
    check("empty name rejected", True)

threads = [threading.Thread(target=lambda n=n: store.append("conc", [(n * 1000 + i, "x") for i in range(200)])) for n in range(8)]
[t.start() for t in threads]
[t.join() for t in threads]
times = [e.t for e in store.query("conc", limit=10_000)]
check("concurrent appends all stored, sorted", len(times) == 1600 and times == sorted(times))
store.clear()
check("clear", store.list_logs() == [])

check("parse int ms", wl.parse_time_ms(1234) == 1234)
check("parse digit string", wl.parse_time_ms("1234") == 1234)
check("parse Z", wl.parse_time_ms("1970-01-01T00:00:01Z") == 1000)
expected = int(datetime(2026, 1, 2, 3, 4, 5).timestamp() * 1000)
check("parse naive = local", wl.parse_time_ms("2026-01-02T03:04:05") == expected)
check("parse offset", wl.parse_time_ms("1970-01-01T01:00:01+01:00") == 1000)
for bad in ("garbage", None, True):
    try:
        wl.parse_time_ms(bad)
        check(f"reject {bad!r}", False)
    except ValueError:
        check(f"reject {bad!r}", True)
check("format_time_iso round-trips", wl.parse_time_ms(wl.format_time_iso(1_700_000_000_123)) == 1_700_000_000_123)

rid = wl.new_recording_id(42)
check("recording id shape", rid.startswith("rec-42-") and rid != wl.new_recording_id(42))
check("recording payload", wl.recording_payload(rid, 42) == {"recording_id": rid, "started_at_ms": 42})
check("stopped payload", wl.stopped_recording_payload(rid, 42, 99) == {"recording_id": rid, "started_at_ms": 42, "stopped_at_ms": 99})
sys.exit(1 if failures else 0)
