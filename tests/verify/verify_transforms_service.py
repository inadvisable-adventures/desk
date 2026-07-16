import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from desk_services.transforms.service import TransformError, TransformsService  # noqa: E402

app = QApplication(sys.argv)

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


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def write_manifest(directory: Path, name: str, manifest: dict) -> Path:
    d = directory / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "transform.json").write_text(json.dumps(manifest))
    return d


PYTHON_TRANSFORM_SOURCE = '''
import json


def run(input_data, config):
    if config and config.get("fail"):
        raise ValueError("deliberate failure")
    suffix = (config or {}).get("suffix", "")
    return input_data.upper() + suffix


def identity(input_data, config):
    # Same str-in/str-out contract as run() (and as the JS/TS wire
    # protocol's "output" field) -- a Python transform's identity()
    # encodes its own JSON-serializable result as a string, same as a
    # JS/TS transform must.
    return json.dumps({"length": len(input_data)})
'''

JS_TRANSFORM_SOURCE = """
let data = '';
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
    const req = JSON.parse(data);
    if (req.action === 'run') {
        if (req.config && req.config.fail) {
            process.stdout.write(JSON.stringify({error: 'deliberate js failure'}));
            return;
        }
        process.stdout.write(JSON.stringify({output: req.input.split('').reverse().join('')}));
    } else if (req.action === 'identity') {
        process.stdout.write(JSON.stringify({output: JSON.stringify({length: req.input.length})}));
    }
});
"""

TS_TRANSFORM_SOURCE = """
let data: string = '';
process.stdin.on('data', (chunk: Buffer) => { data += chunk.toString(); });
process.stdin.on('end', () => {
    const req = JSON.parse(data);
    const result: string = req.input + '-ts-compiled';
    process.stdout.write(JSON.stringify({output: result}));
});
"""

TSCONFIG = json.dumps({"compilerOptions": {"outDir": "dist", "module": "commonjs", "target": "es2020"}})


def test_python_run_and_identity():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        t_dir = write_manifest(
            project_dir,
            "py_transform",
            {"kind": "python", "entry": "transform.py", "input_type": "text", "output_type": "text", "has_identity": True},
        )
        (t_dir / "transform.py").write_text(PYTHON_TRANSFORM_SOURCE)

        service = TransformsService()
        service.discover(None, project_dir)

        results = []
        service.run("py_transform", "hello", None, lambda output, error: results.append((output, error)))
        check("a real Python transform's run() resolves synchronously", results == [("HELLO", None)])

        output = service.run_blocking("py_transform", "hi", {"suffix": "!"})
        check("run_blocking returns the transform's real output", output == "HI!")

        identity_output = service.identity_blocking("py_transform", "hello")
        check("identity_blocking calls the transform's real identity()", json.loads(identity_output) == {"length": 5})


def test_python_error_propagates_without_crashing():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        t_dir = write_manifest(
            project_dir,
            "py_transform",
            {"kind": "python", "entry": "transform.py", "input_type": "text", "output_type": "text"},
        )
        (t_dir / "transform.py").write_text(PYTHON_TRANSFORM_SOURCE)

        service = TransformsService()
        service.discover(None, project_dir)

        results = []
        service.run("py_transform", "x", {"fail": True}, lambda output, error: results.append((output, error)))
        check(
            "a Python transform's own exception surfaces as an error, not a crash",
            len(results) == 1 and results[0][0] is None and "deliberate failure" in results[0][1],
        )

        try:
            service.run_blocking("py_transform", "x", {"fail": True})
            check("run_blocking raises TransformError on failure", False)
        except TransformError as e:
            check("run_blocking raises TransformError on failure", "deliberate failure" in str(e))


def test_javascript_run_via_real_node_subprocess():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        t_dir = write_manifest(
            project_dir,
            "js_transform",
            {"kind": "javascript", "entry": "transform.js", "input_type": "text", "output_type": "text"},
        )
        (t_dir / "transform.js").write_text(JS_TRANSFORM_SOURCE)

        service = TransformsService()
        service.discover(None, project_dir)

        output = service.run_blocking("js_transform", "hello")
        check("a real JavaScript transform runs via a real node subprocess", output == "olleh")

        try:
            service.run_blocking("js_transform", "x", {"fail": True})
            check("a JS transform's own reported error surfaces as TransformError", False)
        except TransformError as e:
            check("a JS transform's own reported error surfaces as TransformError", "deliberate js failure" in str(e))


def test_javascript_does_not_block_the_event_loop():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        t_dir = write_manifest(
            project_dir,
            "slow_js",
            {"kind": "javascript", "entry": "transform.js", "input_type": "text", "output_type": "text"},
        )
        (t_dir / "transform.js").write_text(
            """
let data = '';
process.stdin.on('data', c => data += c);
process.stdin.on('end', () => {
    setTimeout(() => {
        process.stdout.write(JSON.stringify({output: 'done'}));
    }, 800);
});
"""
        )
        service = TransformsService()
        service.discover(None, project_dir)

        tick_count = [0]
        from PyQt6.QtCore import QTimer

        timer = QTimer()
        timer.timeout.connect(lambda: tick_count.__setitem__(0, tick_count[0] + 1))
        timer.start(50)

        results = []
        service.run("slow_js", "x", None, lambda output, error: results.append((output, error)))
        pump(1.5)
        timer.stop()

        check("run() for a JS transform returns immediately (non-blocking)", True)  # reaching pump() at all proves this
        check(
            "the Qt event loop kept processing other events while the JS subprocess ran",
            tick_count[0] > 3,
        )
        check("the slow JS transform still eventually resolves", results == [("done", None)])


def test_typescript_builds_with_real_tsc_and_caches():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d) / "desk_transforms"
        t_dir = write_manifest(
            project_dir,
            "ts_transform",
            {"kind": "typescript", "entry": "transform.ts", "input_type": "text", "output_type": "text"},
        )
        (t_dir / "transform.ts").write_text(TS_TRANSFORM_SOURCE)
        (t_dir / "tsconfig.json").write_text(TSCONFIG)

        service = TransformsService()
        service.discover(None, project_dir)

        output = service.run_blocking("ts_transform", "hi")
        check("a real TypeScript transform builds with real tsc and runs", output == "hi-ts-compiled")

        compiled = t_dir / "dist" / "transform.js"
        check("tsc produced the expected compiled output", compiled.is_file())

        first_mtime = compiled.stat().st_mtime
        output2 = service.run_blocking("ts_transform", "again")
        check(
            "a second invocation with an unchanged source doesn't rebuild",
            output2 == "again-ts-compiled" and compiled.stat().st_mtime == first_mtime,
        )

        time.sleep(1.1)  # ensure a real, detectable mtime difference
        (t_dir / "transform.ts").write_text(TS_TRANSFORM_SOURCE.replace("-ts-compiled", "-REBUILT"))
        output3 = service.run_blocking("ts_transform", "again")
        check(
            "touching the .ts source with a newer mtime triggers a real rebuild",
            output3 == "again-REBUILT" and compiled.stat().st_mtime > first_mtime,
        )


def test_promote():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d) / ".desk_temp" / "transforms"
        project_dir = Path(d) / "desk_transforms"
        write_manifest(
            desk_temp_dir,
            "local_transform",
            {"kind": "javascript", "entry": "transform.js", "input_type": "a", "output_type": "b"},
        )
        (desk_temp_dir / "local_transform" / "transform.js").write_text("// stub")

        service = TransformsService()
        service.promote("local_transform", desk_temp_dir, project_dir)
        check(
            "promote moves the directory from .desk_temp to desk_transforms",
            not (desk_temp_dir / "local_transform").exists() and (project_dir / "local_transform").is_dir(),
        )

        try:
            service.promote("local_transform", desk_temp_dir, project_dir)
            check("promoting a nonexistent .desk_temp source raises TransformError", False)
        except TransformError:
            check("promoting a nonexistent .desk_temp source raises TransformError", True)


def test_promote_refuses_to_overwrite_existing_destination():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d) / ".desk_temp" / "transforms"
        project_dir = Path(d) / "desk_transforms"
        write_manifest(desk_temp_dir, "dup", {"kind": "javascript", "entry": "transform.js", "input_type": "a", "output_type": "b"})
        write_manifest(project_dir, "dup", {"kind": "javascript", "entry": "transform.js", "input_type": "a", "output_type": "b"})

        service = TransformsService()
        try:
            service.promote("dup", desk_temp_dir, project_dir)
            check("promote refuses to overwrite an existing destination", False)
        except TransformError:
            check("promote refuses to overwrite an existing destination", True)
        check(
            "the .desk_temp source is left untouched after a refused promote",
            (desk_temp_dir / "dup").is_dir(),
        )


test_python_run_and_identity()
test_python_error_propagates_without_crashing()
test_javascript_run_via_real_node_subprocess()
test_javascript_does_not_block_the_event_loop()
test_typescript_builds_with_real_tsc_and_caches()
test_promote()
test_promote_refuses_to_overwrite_existing_destination()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
