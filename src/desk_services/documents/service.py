"""`desk.documents` v1 (TODO 8e4711e): virtualized, Desk-cached raw byte-range
reads of large or binary files. See plans/desk-documents-v1.md.

Qt-free and thread-safe (the Bridge API calls it from server threads, a
`kind: "python"` widget from the GUI thread). No format awareness: handles and
raw byte ranges only.
"""
import base64
import hashlib
import os
import secrets
import shutil
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MAX_READ_BYTES = 8 * 1024 * 1024
MAX_HANDLES = 256
MAX_CACHE_BYTES_PER_DOCUMENT = 64 * 1024 * 1024


class DocumentsError(Exception):
    """A problem the caller should see verbatim (bad handle, bad range, not a file)."""


@dataclass
class _Doc:
    path: Path
    owner: str | None


class DocumentsService:
    def __init__(
        self,
        directory_provider: Callable[[], Path | None] | None = None,
        cache_root_provider: Callable[[], Path | None] | None = None,
    ) -> None:
        self._directory_provider = directory_provider
        self._cache_root_provider = cache_root_provider
        self._lock = threading.Lock()
        self._handles: OrderedDict[str, _Doc] = OrderedDict()
        # path -> the cache key currently valid for it (to delete the old
        # directory when the file changes).
        self._current_key: dict[Path, str] = {}

    def configure(
        self,
        directory_provider: Callable[[], Path | None],
        cache_root_provider: Callable[[], Path | None],
    ) -> None:
        self._directory_provider = directory_provider
        self._cache_root_provider = cache_root_provider

    # -- handles ---------------------------------------------------------------------

    def resolve(self, raw_path: str) -> Path:
        """Like desk.fs.*: a relative path resolves against the current
        Desk's directory; an absolute one is used as-is."""
        path = Path(raw_path)
        if path.is_absolute():
            return path
        directory = self._directory_provider() if self._directory_provider is not None else None
        return (directory / path) if directory is not None else path

    def open(self, path: str | Path, owner: str | None = None) -> str:
        resolved = self.resolve(str(path))
        if not resolved.is_file():
            raise DocumentsError(f"Not a readable file: {resolved}")
        handle = secrets.token_hex(8)
        with self._lock:
            self._handles[handle] = _Doc(resolved, owner)
            while len(self._handles) > MAX_HANDLES:
                self._handles.popitem(last=False)
        return handle

    def close(self, handle: str) -> bool:
        with self._lock:
            return self._handles.pop(handle, None) is not None

    def open_handles(self) -> int:
        with self._lock:
            return len(self._handles)

    # -- reads ---------------------------------------------------------------------------

    def read_bytes(self, handle: str, offset: int, length: int) -> tuple[bytes, bool]:
        """(bytes, eof) for [offset, offset+length) -- length clamped to
        MAX_READ_BYTES, served from the cache when this exact range was
        already read from this exact version of the file."""
        if offset < 0 or length < 0:
            raise DocumentsError("offset and length must be non-negative")
        length = min(length, MAX_READ_BYTES)
        with self._lock:
            doc = self._handles.get(handle)
        if doc is None:
            raise DocumentsError(f"Unknown or closed document handle: {handle!r}")
        try:
            stat = doc.path.stat()
        except OSError as exc:
            raise DocumentsError(str(exc)) from exc
        key = hashlib.sha1(f"{doc.path}|{stat.st_mtime_ns}|{stat.st_size}".encode()).hexdigest()
        cache_dir = self._cache_dir(key)
        self._invalidate_previous(doc.path, key)
        entry = cache_dir / f"{offset}_{length}" if cache_dir is not None else None
        if entry is not None and entry.is_file():
            data = entry.read_bytes()
        else:
            try:
                with open(doc.path, "rb") as f:
                    f.seek(offset)
                    data = f.read(length)
            except OSError as exc:
                raise DocumentsError(str(exc)) from exc
            if entry is not None and data:
                self._store(cache_dir, entry, data)
        return data, offset + len(data) >= stat.st_size

    def read(self, handle: str, offset: int = 0, length: int = MAX_READ_BYTES) -> dict:
        """The Bridge API shape: {"data": base64, "eof": bool}."""
        data, eof = self.read_bytes(handle, offset, length)
        return {"data": base64.b64encode(data).decode("ascii"), "eof": eof}

    # -- cache -----------------------------------------------------------------------------

    def _cache_dir(self, key: str) -> Path | None:
        root = self._cache_root_provider() if self._cache_root_provider is not None else None
        return (root / key) if root is not None else None

    def _invalidate_previous(self, path: Path, key: str) -> None:
        with self._lock:
            previous = self._current_key.get(path)
            self._current_key[path] = key
        if previous is not None and previous != key:
            old = self._cache_dir(previous)
            if old is not None:
                shutil.rmtree(old, ignore_errors=True)

    def _store(self, cache_dir: Path, entry: Path, data: bytes) -> None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = entry.with_name(entry.name + f".tmp{secrets.token_hex(4)}")
            tmp.write_bytes(data)
            os.replace(tmp, entry)
            self._evict(cache_dir)
        except OSError:
            pass  # the cache is an optimization; never fail a read over it

    def _evict(self, cache_dir: Path) -> None:
        files = [p for p in cache_dir.iterdir() if p.is_file() and ".tmp" not in p.name]
        total = sum(p.stat().st_size for p in files)
        for p in sorted(files, key=lambda f: f.stat().st_mtime):
            if total <= MAX_CACHE_BYTES_PER_DOCUMENT:
                break
            total -= p.stat().st_size
            p.unlink(missing_ok=True)


_service = DocumentsService()


def get_service() -> DocumentsService:
    return _service
