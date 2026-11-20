"""TODO b9689cd: scripts/build_desk_recorder_app.sh builds a signed DeskRecorder.app whose launcher runs
the python recorder as a child, forwards arguments, exposes the permission channel and propagates the
exit status. A wrapper script stands in for python and only asks for an UNKNOWN permission (answered
`denied`), so no real macOS prompt is triggered."""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


if sys.platform != "darwin" or not shutil.which("clang"):
    print("SKIP: needs macOS with clang")
    sys.exit(0)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    log = tmp / "app.log"
    wrapper = tmp / "fakepython.sh"
    wrapper.write_text(
        "#!/bin/bash\n"
        'echo "ARGS: $@"\n'
        'echo "PYTHONPATH: $PYTHONPATH"\n'
        'echo "PWD: $PWD"\n'
        'echo "FD: $DESK_RECORDER_PERM_FD"\n'
        'eval "echo bogus >&$DESK_RECORDER_PERM_FD"\n'
        'eval "read -u $DESK_RECORDER_PERM_FD reply"\n'
        'echo "REPLY: $reply"\n'
        "exit 7\n"
    )
    wrapper.chmod(0o755)
    env = dict(os.environ, DESK_RECORDER_PYTHON=str(wrapper), DESK_RECORDER_LOG=str(log))
    out = tmp / "out"
    r = subprocess.run([str(REPO / "scripts/build_desk_recorder_app.sh"), "--output", str(out), "--no-install"],
                       capture_output=True, text=True, env=env)
    app = out / "DeskRecorder.app"
    check("the build script succeeds", r.returncode == 0 and app.is_dir())
    check("--no-install leaves ~/Applications alone", "installed" not in r.stdout)
    exe = app / "Contents/MacOS/DeskRecorder"
    check("the launcher executable exists", exe.is_file() and os.access(exe, os.X_OK))
    plist = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    check("Info.plist has the bundle id and executable", plist["CFBundleIdentifier"] == "local.desk.recorder" and plist["CFBundleExecutable"] == "DeskRecorder")
    check("Info.plist explains the camera and microphone", bool(plist.get("NSCameraUsageDescription")) and bool(plist.get("NSMicrophoneUsageDescription")))
    check("Info.plist hides the app from the Dock", plist.get("LSUIElement") is True)
    check("Info.plist opts in to Continuity Camera", plist.get("NSCameraUseContinuityCameraDeviceType") is True)
    sig = subprocess.run(["codesign", "-d", "-r-", str(app)], capture_output=True, text=True)
    check("signed with a bundle-id designated requirement", 'identifier "local.desk.recorder"' in sig.stdout + sig.stderr)
    verify = subprocess.run(["codesign", "--verify", "--strict", str(app)], capture_output=True, text=True)
    check("the signature verifies", verify.returncode == 0)

    run = subprocess.run([str(exe), "--socket", "/x/y z", "-psn_0_12345"], capture_output=True, text=True, timeout=30)
    text = log.read_text()
    check("the child's exit status is the launcher's", run.returncode == 7)
    check("the child is run as `python -m desk.recorder_app <args>`", "ARGS: -m desk.recorder_app --socket /x/y z" in text)
    check("LaunchServices' -psn argument is not forwarded", "-psn" not in text)
    check("PYTHONPATH points at the checkout's src", f"PYTHONPATH: {REPO}/src" in text)
    check("the child runs in the checkout directory", f"PWD: {REPO}" in text)
    check("the permission channel fd is passed", "FD: " in text and text.split("FD: ")[1].split("\n")[0].strip().isdigit())
    check("an unknown permission is answered `denied`", "REPLY: denied" in text)
    run2 = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    check("a second run appends to the log", log.read_text().count("ARGS:") == 2 and run2.returncode == 7)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
