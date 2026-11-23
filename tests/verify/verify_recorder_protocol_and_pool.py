"""TODO b9689cd: the DeskRecorder line protocol and the transcript pool."""
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from desk import recorder_protocol as proto  # noqa: E402
from desk import transcript_pool as pool  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


# --- protocol ---
for name, fields in [
    ("start-screen", ("window:Desk%20-%20x", "/tmp/a b/c.mp4")),
    ("start-camera", ("default", "/x/y.mp4")),
    ("start-transcribe", ("rec-1-ab", "/p q/pool")),
    ("stop", ("screen",)),
    ("status", ()),
    ("final", ("rec-1-ab", "100", "200", "hello  there, \"world\" é")),
    ("error", ("camera", "permission denied: needs Camera access")),
    ("stopped", ("screen", "")),
    ("state", ("transcribe", "running", "")),
    ("heartbeat", ("1700000000000",)),
    ("preview-frame", ("screen", "/9j/4AAQSkZJRgABAQAAAQABAAD//gA7Q1JFQVRP")),  # TODO d95a323
]:
    check(f"round trip {name}", proto.decode(proto.encode(name, *fields)) == proto.Message(name, tuple(fields)))
check("trailing free text keeps its spaces", proto.decode("final s 1 2 a  b c").fields[3] == "a  b c")
check("encode appends exactly one newline", proto.encode("status") == b"status\n")
check("newline in a field is rejected", raises(lambda: proto.encode("error", "screen", "a\nb"), proto.ProtocolError))
check("space in a non-last field is rejected", raises(lambda: proto.encode("start-screen", "a b", "p"), proto.ProtocolError))
check("empty non-last field is rejected", raises(lambda: proto.encode("start-screen", "", "p"), proto.ProtocolError))
check("wrong field count is rejected", raises(lambda: proto.encode("stop"), proto.ProtocolError))
check("unknown message is rejected (encode)", raises(lambda: proto.encode("nope"), proto.ProtocolError))
check("unknown message is rejected (decode)", raises(lambda: proto.decode("nope x"), proto.ProtocolError))
check("too few fields is rejected (decode)", raises(lambda: proto.decode("stop"), proto.ProtocolError))
check("CRLF is tolerated", proto.decode(b"stop screen\r\n") == proto.Message("stop", ("screen",)))
check("quote/unquote round trip", proto.unquote_token(proto.quote_token("My Window - é/x")) == "My Window - é/x")
check("quoted token has no spaces", " " not in proto.quote_token("a b c"))

# --- pool ---
with tempfile.TemporaryDirectory() as tmp:
    desk_dir = Path(tmp)
    p = pool.pool_dir(desk_dir)
    check("pool dir under .desk_temp", p == desk_dir / ".desk_temp" / "transcript-pool")
    check("empty pool lists nothing", pool.list_sessions(p) == [])
    check("missing session reads empty", pool.read_records(p, "rec-1-aa") == ([], 0))
    s = "rec-1000-ab"
    pool.append_segment(p, pool.Segment(s, 0, 1000, 1500, "hel", False))
    pool.append_segment(p, pool.Segment(s, 0, 1000, 1800, "hello there", True))
    pool.append_segment(p, pool.Segment(s, 1, 2000, 2500, "second é \"q\"\nline", True))
    records, offset = pool.read_records(p, s)
    check("all three raw records are read", len(records) == 3 and offset > 0)
    collapsed = pool.collapse(records)
    check("collapse: last record per seq wins", [(c.seq, c.text, c.final) for c in collapsed][0] == (0, "hello there", True))
    check("collapse: ordered by seq, one per seq", [c.seq for c in collapsed] == [0, 1])
    check("text with a newline/quote survives", collapsed[1].text == "second é \"q\"\nline")
    check("read_collapsed matches", pool.read_collapsed(p, s) == collapsed)
    more, offset2 = pool.read_records(p, s, offset)
    check("tailing from the returned offset finds nothing new", more == [] and offset2 == offset)
    pool.append_segment(p, pool.Segment(s, 2, 3000, 3100, "third", True))
    more, offset3 = pool.read_records(p, s, offset)
    check("tailing finds only the new record", [m.seq for m in more] == [2] and offset3 > offset)
    # a half-written line is not consumed
    with open(pool.session_path(p, s), "ab") as f:
        f.write(b'{"session": "x", "seq": 9, "start_')
    more, offset4 = pool.read_records(p, s, offset3)
    check("a partial last line is left for later", more == [] and offset4 == offset3)
    with open(pool.session_path(p, s), "ab") as f:
        f.write(b'ms": 1, "end_ms": 2, "text": "ok", "final": true}\n')
    more, _ = pool.read_records(p, s, offset3)
    check("the completed line is read next time", [m.seq for m in more] == [9])
    with open(pool.session_path(p, s), "ab") as f:
        f.write(b"not json\n")
    more, _ = pool.read_records(p, s, 0)
    check("a corrupt line is skipped", [m.seq for m in more].count(9) == 1 and len(more) == 5)
    pool.append_segment(p, pool.Segment("rec-2000-cd", 0, 5, 6, "other", True))
    check("list_sessions lists both, oldest first", [x.session for x in pool.list_sessions(p)] == [s, "rec-2000-cd"])
    for bad in ["../x", "a/b", "", "..", "x" * 101]:
        check(f"invalid session id {bad[:12]!r} rejected", not pool.valid_session_id(bad))
    check("session_path rejects traversal", raises(lambda: pool.session_path(p, "../x"), ValueError))

    # many concurrent readers, one writer
    s2 = "rec-3000-ef"
    stop = threading.Event()
    results = []

    def reader():
        off, seen = 0, []
        while not stop.is_set() or True:
            recs, off = pool.read_records(p, s2, off)
            seen += [r.seq for r in recs]
            if stop.is_set():
                recs, off = pool.read_records(p, s2, off)
                seen += [r.seq for r in recs]
                break
        results.append(seen)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for i in range(200):
        pool.append_segment(p, pool.Segment(s2, i, i, i + 1, f"t{i}", True))
    stop.set()
    for t in threads:
        t.join()
    check("4 concurrent readers each see all 200 records in order", all(r == list(range(200)) for r in results) and len(results) == 4)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
