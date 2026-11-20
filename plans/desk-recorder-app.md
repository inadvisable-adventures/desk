# Plan: TODO `b9689cd` -- DeskRecorder, a stand-alone recorder app with a shared transcript pool (COMPLETED)

## Summary

A stand-alone macOS app, `DeskRecorder.app`, that Desk starts and controls.
It owns the three capture features and asks macOS for each permission only
when its feature is first enabled:

| Feature | macOS permission | Output |
|---|---|---|
| **Transcription** | Microphone | transcript segments in the shared pool |
| **Screen recording** | Screen Recording (+ Microphone for an audio track) | MP4 of a chosen window or screen |
| **Camera video** | Camera | MP4 from a camera device |

Any combination can run: just transcription, just screen, just camera, or all
three. Features start and stop independently. Denying one permission does not
block the others.

Evidence and findings behind this are in `.desk_temp/recording-discussion.2026-11-19.md`
(gitignored): the 30 s spike ran window capture (60 fps), camera (30 fps),
mic recording and whisper (`whisper-large-v3-turbo`, ~1.1 s per 8 s window)
in one Python/Qt process with a ~1 ms p99 GUI lag and ~82% of one core.

## Decisions (mine; say so if you want them otherwise)

1. **One bundle, three lazily requested permissions**, not one app per
   permission. macOS keeps a separate grant per service per app anyway, so
   one bundle already gives "one permission per feature". Two bundles would
   only make sense to give the camera a separate System Settings entry.
2. **First version is Python + Qt (the code proven in the spike), wrapped in a
   small Objective-C launcher**, not a rewrite in Swift. The spike showed no
   performance need, and CLAUDE.md prefers no new dependencies. The control
   protocol is language-neutral so a Swift helper can replace the Python
   recorder later without touching Desk (see "Later" below).
3. **The launcher must request the permissions** (`AVCaptureDevice
   requestAccessForMediaType`, `CGRequestScreenCaptureAccess`): the spike
   found Qt multimedia refuses to ask from a Python child process because
   the child has no `NSCameraUsageDescription`. Each is requested when its
   feature is enabled, not at app start.
4. **Run the Python as a child of the launcher** (not `exec`), so TCC grants
   attach to the app. The app is signed ad hoc with the designated
   requirement `identifier "<bundle id>"` so rebuilds keep the grants (the
   spike did not confirm that; test it).
5. **Control protocol is plain text lines, not JSON** (user preference), over
   a Unix domain socket the app creates and Desk connects to.

## Components

### 1. The app (`desk_recorder/`, built by `scripts/build_desk_recorder_app.sh`)

- `launcher.m`: requests permissions on command, spawns the Python recorder
  as a child, forwards its exit status. Based on the spike's `launcher.m`.
- `recorder.py`: the Qt process. One `QMediaCaptureSession` per video source
  (window, camera) with its own `QMediaRecorder`; a separate 16 kHz mono
  `QAudioSource` for whisper (the spike showed opening the mic twice works).
- Each feature is an independent object with `start(opts)`, `stop()` and a
  status string. Starting a feature requests its permission first; a denial
  reports `error <feature> permission-denied` and leaves the others alone.
- Output files go to a directory given by Desk (default under the project).

### 2. Control protocol (text lines over a Unix socket)

Commands from Desk: `start screen <target> <path>`, `start camera <device> <path>`,
`start transcribe`, `stop <feature>`, `status`, `quit`.
Events from the app: `started <feature>`, `stopped <feature> <path>`,
`error <feature> <reason>`, `status <feature> <state> ...`,
`dropped <feature> <n>`, `heartbeat`.
Free text (paths, messages) is the last field on a line; reject newlines in
paths. Transcript text is NOT sent over this socket -- it goes to the pool.

### 3. The Desk side

- A supervisor (`desk.recorder_client` or similar) that starts the app with
  `open -n -a DeskRecorder.app --args --socket <path>` (so macOS attributes
  permissions to the app, not to Terminal), connects, sends commands, and
  watches heartbeats. It restarts nothing silently: a lost heartbeat is shown.
- A way to drive it: Bridge API (`desk.recorder.start/stop/status`) with a
  capability, plus MCP tools, following `desk.agents.launch` (TODO `507b8d5`).
- A small built-in widget with one toggle per feature, the permission state
  of each, and the latest status. Follows `python-widget-conventions.md`.

### 4. The shared transcript pool

Transcription writes **segments** to a pool that any widget can read.

- **Storage:** an append-only file per recording session in a pool directory
  inside the project (location chosen at implementation, following wherever
  voice recordings already live), one segment per line. Segment fields:
  session id, segment id, start and end time on the recorder's clock,
  wall-clock start in ms, text, `final` or `provisional`, and which
  recording files the session overlaps (so a transcript can be located in
  video). The pool is local and gitignored: transcripts are sensitive.
- **Segmentation:** cut at pauses (voice-activity endpointing), commit
  finished segments, mark the trailing words provisional. The
  1-second-per-call whisper cost and flicker from
  `investigations/live_transcription_chunking.md` still apply.
- **Reading:** a Python module for Python widgets and `desk.transcripts`
  (`list`, `read`, `subscribe`) in the Bridge client for html widgets, both
  over the same files. Live updates arrive through the existing event
  channel. Because the files are append-only and every reader keeps its own
  position, any number of widgets can read at once.

## Verification

Headless, no real devices needed:
- protocol parser/formatter round-trip, newline rejection;
- supervisor driving a fake recorder that speaks the protocol (start/stop each
  feature independently and in combination; permission-denied for one feature
  leaves the others running; lost heartbeat);
- pool: segment write/read, provisional-to-final replacement, concurrent
  readers, partial last line tolerated, session listing;
- Bridge routes and `desk.transcripts` client against a real server;
- the build script produces a signed bundle with the expected `Info.plist`
  keys and designated requirement.

Cannot be verified headlessly and must be done by hand once: the three
permission prompts, a real recording of each feature alone and all together,
that grants survive a rebuild, and that transcript timestamps line up with
the video.

## Later (not in this TODO)

- Replace the Python recorder with a Swift helper if a long, real-Desk run
  shows drops (the spike was 30 s with a synthetic window).
- Separate whisper process fed from a shared-memory ring buffer
  (`.desk_temp/recording-discussion.2026-11-19.md`).
- Compositing the camera into the screen video; one multi-track file.
- Checking that popups are captured with the Desk window.
- Developer-ID signing and notarization.

## As built (2026-11-20) -- where it differs from the plan above

- **Desk listens, the app connects.** `RecorderService` creates the Unix
  socket and starts the app with `--socket <path>`; a connection means the
  app is up and a closed one means it died. (The plan had the app create it.)
- **Permissions go through the launcher over a socket pair.** The Python
  child cannot ask (no Info.plist), so it writes `camera|microphone|screen`
  to `DESK_RECORDER_PERM_FD` and the Objective-C launcher answers `granted`,
  `denied` or `restart`. They are requested when the feature starts, off the
  Qt main thread so the heartbeat keeps going during a prompt.
- **The pool is plain files plus the existing widget logs.** `final`
  protocol events (a notification only; the text is also in the pool) are
  mirrored into the existing `WidgetLogStore` under the log name
  `transcript`, so `desk_query_widget_log` already works on them. No new
  store was invented; `desk.transcripts` reads the files.
- **Qt quirks found:** PyQt6 cannot connect `QMediaRecorder`'s
  `errorOccurred` or `recorderStateChanged` to a Python callable, so the
  recorder state is polled every 100 ms and `errorChanged` is used.
- **`dropped`** counts stalls (gaps over 100 ms between frames reaching the
  sink), not frames known to be missing from the file.
- **Segments:** energy-based pause detection, pre-roll, provisional every
  2 s, forced cut at 25 s; a whisper guard drops segments whisper itself
  rates as not speech and low confidence.
- **MCP tools** `desk_recorder_status`, `desk_recorder_control` (records the
  user's microphone, screen or camera; its description says to use it only
  when asked) and `desk_read_transcript`.
- **Install:** `scripts/build_desk_recorder_app.sh` builds into `build/` and
  installs to `~/Applications/DeskRecorder.app` (`--no-install`,
  `--output DIR`). The checkout path and `.venv` python are baked in.
- **Cosmetic:** the app is `LSUIElement` (no Dock icon) but the Python child
  is a Qt GUI process and may still show one.

## Not verified

- A real recording of screen or camera, and real transcription through the
  app (whisper plus the microphone). The pipeline is tested with a synthetic
  WAV and a stub transcriber; the real app was started through
  LaunchServices and listed sources, but its first microphone request
  waited for a permission answer that never came during the attempt.
- Any macOS permission prompt for `local.desk.recorder`; that grants survive
  a rebuild; Screen Recording after the required restart.
- Transcript times lining up with the video; popups in window capture; a
  long recording.
