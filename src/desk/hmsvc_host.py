"""Entry point a Desk-hosted microservice subprocess runs (TODO
e75b165): `python -m desk.hmsvc_host <service_dir> <port>`. Loads
`<service_dir>/service.py`, takes its module-level ASGI `app`, and
serves it with uvicorn on <host>:<port> (host defaults to 127.0.0.1;
`0.0.0.0` for a service with `"external": true`). See desk.hmsvc."""

import importlib.util
import sys
from pathlib import Path

import uvicorn

from desk.hmsvc import SERVICE_ENTRY_FILENAME


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print("usage: python -m desk.hmsvc_host <service_dir> <port> [host]", file=sys.stderr)
        return 2
    host = argv[3] if len(argv) == 4 else "127.0.0.1"
    directory = Path(argv[1]).resolve()
    port = int(argv[2])
    entry = directory / SERVICE_ENTRY_FILENAME
    # The service's own directory first, so `import helper` beside
    # service.py works.
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location(f"desk_hmsvc_{directory.name}", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = getattr(module, "app", None)
    if app is None:
        print(f"{entry}: no module-level ASGI `app` found", file=sys.stderr)
        return 3
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
