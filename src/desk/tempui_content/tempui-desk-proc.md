# TempUI DSL: DeskProc

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
just covers the `DeskProc` keyword.

For running a **one-time Python script** with real, in-process access
to Desk's own live shell -- reveal a specific already-placed widget
instance (the same action as clicking its titlebar eye button), take a
real pixel screenshot of one, or list what's currently placed --
instead of just a `kind: "html"` widget's own capability-scoped Bridge
API, which has no equivalent of any of that. If your script only needs
Bridge API access (`workspace`, `fs`, `state`, ...), reach for `Job`
(see `tempui-jobs.md`) instead -- that's the general-purpose one-time
-script mechanism; `DeskProc` exists specifically for the subset of
actions that require touching Desk's shell directly, which a
sandboxed `kind: "html"` page structurally cannot do. Like `Job`, this
is a single one-shot run, not a reusable, promotable widget *kind*.

- The first line is `DeskProc<TAB>summary` -- `summary` is shown in the
  notification and the placed Desk Proc Runner widget, never executed.
- One or more `Script<TAB>base64-chunk` lines -- your script's entire
  source, base64-encoded (chunk it across several `Script` lines for a
  long script; concatenated in file order before decoding, the same
  convention `Job`'s own `Script` lines and `DefineWidget`'s own `Html`
  lines already use). Always a plain Python script -- there is no
  `html`-kind variant of `DeskProc` at all. Executed directly (no
  `desk` package import needed beyond what you'd already use in any
  other Python code in this environment) -- there is no capability
  scoping here, the same "no sandboxing" trust level `Job`'s own
  `python` kind already has. "View Code is the only review step" for
  this mechanism too.

Your script's exec namespace also gets a `deskproc` global -- the
*documented*, safe way to act on Desk's own shell from your script
(which runs on a background thread; touching a Qt widget directly from
there is unsafe, so use these methods rather than trying to reach into
`desk.shell.window`/`desk.shell.canvas` yourself):

- `deskproc.reveal_widget(instance_id: str) -> bool` -- zooms/pans the
  Workspace Canvas so the given placed widget instance fills the view,
  the same action as clicking that instance's own titlebar eye button.
  Returns whether a matching instance was found.
- `deskproc.screenshot_widget(instance_id: str, path: str, max_width:
  int | None = None) -> bool` -- saves a real PNG screenshot of that
  instance's own placed frame (titlebar and content, exactly as it
  looks on the canvas) to `path`. A relative `path` resolves against
  the current Desk's own directory, same as `desk.fs.writeFile`;
  missing parent directories are created automatically. `max_width`,
  if given, scales the capture down proportionally to at most that
  many pixels wide before saving -- never up, and omitting it keeps
  today's native-resolution capture (often HiDPI 2x) exactly as-is; ask
  for a smaller `max_width` when you only need "good enough to see
  what's on screen," not a pixel-perfect native-resolution image (a
  full native canvas capture, base64-encoded for transport, can run to
  several hundred KB). Returns whether the instance was found and the
  file was saved successfully.
- `deskproc.screenshot_desk(path: str, max_width: int | None = None)
  -> bool` -- saves a real PNG screenshot of the whole Workspace Canvas
  viewport (not any native window chrome around it) to `path`, same
  path-resolution rules and `max_width` downsampling as above.
- `deskproc.list_widget_instances() -> list[dict]` -- the current
  Desk's live placed-widget layout (instance ids, widget kind,
  position, size, and `stale` -- TODO f0da2e9, `true` when that
  instance is showing the titlebar `[STALE]` badge and so is still
  running its own pre-edit code) -- the same data
  `desk.workspace.getState()` already exposes to a `kind: "html"`
  widget with the `workspace` capability, provided here so a script
  has a real way to discover an instance id rather than needing one
  handed in from outside.

Clicking the resulting notification places a **Desk Proc Runner**
widget, showing your declared summary, a "View Code" button (opens
your script's own source in a real editor), and a "Start" button --
**nothing runs until Start is clicked**. Once started, Start becomes
disabled and stays that way (even across a Desk reload) -- a
`DeskProc` is a one-shot run, not a repeatable tool; write a new
`DeskProc` file for a second run.

**This notification looks different from every other tempui kind's
own notification on purpose** -- a distinct border color and a bold
"DESK PROC" caption above the summary -- specifically so a Desk Proc
(real, in-process shell access) is never mistaken at a glance for an
ordinary tempui placement (a widget instance, a question, ...).

You don't have to hand-write the base64/`Script` line(s) below
yourself -- `.desk_temp/build_job_or_desk_proc.py` (mirroring
`build_widget.py`'s convenience for `DefineWidget`) builds a real
`DeskProc` file for you from a plain Python script file:

```
python3 .desk_temp/build_job_or_desk_proc.py desk-proc "Reveal and screenshot the Editor widget" reveal_and_shoot.py
```

prints the path of the tempui file it wrote, ready to be picked up the
same as any other `.desk_temp/` file.

Example (script shown decoded/unwrapped for readability -- the real
file's `Script` line(s) would carry it base64-encoded):

```
DeskProc	Reveal and screenshot the Editor widget
Script	<base64-encoded script text>
```

```python
result = deskproc.screenshot_widget("some-instance-id", "screenshots/editor.png")
print(f"screenshot saved: {result}")
```
