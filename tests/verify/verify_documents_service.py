"""Verifies TODO `8e4711e`: the Qt-free desk.documents service (byte ranges,
cache, invalidation, handles)."""

import base64
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "src")

from desk_services.documents import DocumentsError, DocumentsService  # noqa: E402
from desk_services.documents import service as svc_module  # noqa: E402

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


def raises(fn):
    try:
        fn()
    except DocumentsError as e:
        return str(e)
    return None


BINARY = bytes(range(256)) * 40  # 10240 bytes, not valid UTF-8


def fresh(tmp):
    directory = Path(tmp)
    cache = directory / ".desk_temp" / "documents_cache"
    service = DocumentsService(lambda: directory, lambda: cache)
    path = directory / "big.bin"
    path.write_bytes(BINARY)
    return service, path, cache


def test_ranges_and_eof():
    with tempfile.TemporaryDirectory() as tmp:
        service, path, _cache = fresh(tmp)
        h = service.open(path)
        data, eof = service.read_bytes(h, 0, 100)
        check("a first range is exact raw bytes", data == BINARY[:100] and eof is False)
        data, eof = service.read_bytes(h, 10000, 500)
        check("a range reaching the end reports eof and is short", data == BINARY[10000:] and eof is True)
        data, eof = service.read_bytes(h, len(BINARY), 10)
        check("reading at the end returns nothing with eof", data == b"" and eof is True)
        data, eof = service.read_bytes(h, 99999, 10)
        check("reading past the end likewise", data == b"" and eof is True)
        check("binary bytes survive (not valid UTF-8)", BINARY[:300] == service.read_bytes(h, 0, 300)[0])
        wire = service.read(h, 255, 3)
        check("the Bridge shape is base64 + eof", base64.b64decode(wire["data"]) == BINARY[255:258] and wire["eof"] is False)


def test_errors_and_limits():
    with tempfile.TemporaryDirectory() as tmp:
        service, path, _cache = fresh(tmp)
        h = service.open(path)
        check("a negative offset is rejected", raises(lambda: service.read_bytes(h, -1, 5)) is not None)
        check("a negative length is rejected", raises(lambda: service.read_bytes(h, 0, -5)) is not None)
        check("an unknown handle is a clear error", "Unknown or closed" in (raises(lambda: service.read_bytes("nope", 0, 5)) or ""))
        check("opening a missing file fails", raises(lambda: service.open(Path(tmp) / "missing")) is not None)
        check("opening a directory fails", raises(lambda: service.open(Path(tmp))) is not None)
        big = Path(tmp) / "huge.bin"
        with open(big, "wb") as f:
            f.truncate(svc_module.MAX_READ_BYTES + 5000)
        hb = service.open(big)
        data, eof = service.read_bytes(hb, 0, 10**9)
        check("a huge length is clamped to the per-call maximum", len(data) == svc_module.MAX_READ_BYTES and eof is False)
        check("close forgets the handle", service.close(h) is True and service.close(h) is False)
        check("a closed handle can't be read", raises(lambda: service.read_bytes(h, 0, 5)) is not None)


def test_relative_paths_resolve_against_the_desk():
    with tempfile.TemporaryDirectory() as tmp:
        service, path, _cache = fresh(tmp)
        h = service.open("big.bin")
        check("a relative path resolves against the current Desk directory", service.read_bytes(h, 0, 4)[0] == BINARY[:4])
        h2 = service.open(str(path))
        check("an absolute path is used as-is", service.read_bytes(h2, 0, 4)[0] == BINARY[:4])


def test_cache_hit_does_not_touch_the_file():
    with tempfile.TemporaryDirectory() as tmp:
        service, path, cache = fresh(tmp)
        h = service.open(path)
        service.read_bytes(h, 100, 50)
        check("a read populates the cache under .desk_temp", any(cache.rglob("100_50")))
        real_open = open
        opened = []

        def spying_open(file, *a, **k):
            if str(file) == str(path):
                opened.append(file)
            return real_open(file, *a, **k)

        svc_module.open = spying_open
        try:
            data, _eof = service.read_bytes(h, 100, 50)
        finally:
            del svc_module.open
        check("the repeated range is served without reopening the source", opened == [] and data == BINARY[100:150])


def test_changed_file_invalidates():
    with tempfile.TemporaryDirectory() as tmp:
        service, path, cache = fresh(tmp)
        h = service.open(path)
        before = service.read_bytes(h, 0, 8)[0]
        old_dirs = {p.name for p in cache.iterdir()}
        time.sleep(0.01)
        path.write_bytes(b"NEWCONTENT-" + BINARY)
        os.utime(path, None)
        after, _eof = service.read_bytes(h, 0, 8)
        check("a changed file serves new bytes, not the stale cached ones", before == BINARY[:8] and after == b"NEWCONTENT-"[:8])
        new_dirs = {p.name for p in cache.iterdir()}
        check("the previous version's cache directory is deleted", new_dirs and not (old_dirs & new_dirs))
        path.write_bytes(BINARY + b"x")
        check("a same-mtime size change also invalidates (size is part of the key)", service.read_bytes(h, len(BINARY), 5)[0] == b"x")


def test_cache_is_bounded_and_optional():
    with tempfile.TemporaryDirectory() as tmp:
        service, path, cache = fresh(tmp)
        real = svc_module.MAX_CACHE_BYTES_PER_DOCUMENT
        svc_module.MAX_CACHE_BYTES_PER_DOCUMENT = 300
        try:
            h = service.open(path)
            for offset in range(0, 1000, 100):
                service.read_bytes(h, offset, 100)
                time.sleep(0.002)
        finally:
            svc_module.MAX_CACHE_BYTES_PER_DOCUMENT = real
        files = [p for p in cache.rglob("*") if p.is_file()]
        check("the per-document cache stays within its bound (oldest evicted)", sum(p.stat().st_size for p in files) <= 300 and len(files) >= 1)
        check("the newest range survived eviction", any(p.name == "900_100" for p in files))
        bare = DocumentsService()
        bare_handle = bare.open(path)
        check("with no cache location configured, reads still work", bare.read_bytes(bare_handle, 0, 4)[0] == BINARY[:4])


def test_handle_cap():
    with tempfile.TemporaryDirectory() as tmp:
        service, path, _cache = fresh(tmp)
        handles = [service.open(path) for _ in range(svc_module.MAX_HANDLES + 3)]
        check("open handles are capped, oldest dropped", service.open_handles() == svc_module.MAX_HANDLES and raises(lambda: service.read_bytes(handles[0], 0, 1)) is not None and service.read_bytes(handles[-1], 0, 1)[0] == BINARY[:1])


test_ranges_and_eof()
test_errors_and_limits()
test_relative_paths_resolve_against_the_desk()
test_cache_hit_does_not_touch_the_file()
test_changed_file_invalidates()
test_cache_is_bounded_and_optional()
test_handle_cap()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
