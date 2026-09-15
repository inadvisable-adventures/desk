# Pipe-chained verb DSL: implementation (TODO `63bfd42`) (COMPLETED)

## Summary

TODO `765bd2a` (`plans/pipe-chained-verb-dsl.md`) designed the language
in full -- grammar, argument parsing, value flow, the verb registry/
return-shape convention, the `py:` escape hatch, and error/partial
-failure semantics -- and deliberately left implementation and
transport to a later item. This item is that later item: a real
parser/interpreter module (`src/desk/pipeline_dsl.py`), a small built
-in verb registry with real backing implementations (the design plan's
"Illustrative starter verb catalog" -- `reveal_widget`,
`screenshot_widget`, `screenshot_desk`, `list_widget_instances`,
`open_image` -- implemented in full, since all five already have a safe
existing mechanism to back them), and one delivery mechanism: a new
`desk_run_pipeline` MCP tool on the existing in-process Desk MCP server
(TODO `a762501`), so a `Claude (Desk)`/`claude` agent session can run a
pipeline string directly, the same way it already calls
`desk_reveal_widget`/`desk_screenshot_widget`/etc. individually.

This plan implements the design exactly as `plans/pipe-chained-verb-dsl.md`
specifies it (grammar in its Sec. 1, argument parsing in Sec. 2, value
flow in Sec. 3, verb registry/return-shape in Sec. 4, the `py:` escape
hatch in Sec. 5, error semantics and the result contract in Sec. 6) --
that plan should be read first; this one does not re-derive any of
those decisions, only how they're realized in code.

## Affected files

- **New: `src/desk/pipeline_dsl.py`** -- the parser/interpreter:
  stage-splitting, per-verb-stage argument coercion, the `py:`
  escape hatch, fail-fast execution, and the result-contract dict. Also
  hosts the built-in `VERB_REGISTRY` and its five verb implementations.
- **Modified: `src/desk/shell/desk_mcp_server.py`** -- one new tool,
  `desk_run_pipeline`, a thin wrapper that calls
  `pipeline_dsl.run_pipeline` and returns its result as JSON. Unlike
  every other tool in this file, running a pipeline needs no
  `_call_on_gui_thread` marshaling of its own -- `run_pipeline` runs
  synchronously on the calling (event-loop) thread, and any verb that
  itself needs the GUI thread marshals internally, exactly the way
  `DeskProcApi` (`widgets/desk_proc_runner/widget.py`) already does for
  a Desk Proc script's own background thread. This keeps `run_pipeline`
  itself GUI-thread-agnostic and reusable from a future non-MCP
  transport without change.
- **Modified: `src/desk/temp_ui.py`** -- bump `TEMPUI_DOC_VERSION` to
  44 and add a `_NEW_FEATURES_DOC` "Version 44" entry describing the
  new `desk_run_pipeline` MCP tool (per `development-process.md`'s
  "Keep the tempui changelog docs current" -- a new agent-facing
  capability). No DSL/dropped-file change, so nothing else in that file
  needs touching; the pipeline DSL is not itself a tempui-file keyword.
- **New: `tests/verify/verify_pipeline_dsl.py`** -- parser/interpreter
  unit coverage plus the design plan's own three worked examples run
  for real, using a fake window/`current_context` registration
  (`verify_desk_mcp_server.py`'s own `_FakeWindow`/`_register_fake_window`
  shape, duplicated here rather than imported across test files, matching
  how every other verify script in this directory is self-contained).
- **Modified: `tests/verify/verify_desk_mcp_server.py`** -- add
  coverage for the new `desk_run_pipeline` tool, following that file's
  existing `_FakeWindow`/`check()` pattern.

## Implementation approach

### 1. Stage splitting (`pipeline_dsl._tokenize`)

Per Sec. 1's "equivalently" note: drive one
`shlex.shlex(text, posix=True, punctuation_chars="|")` with
`whitespace_split = True` over the whole pipeline string, producing a
flat token list where a bare `|` is its own token and a quoted `|` (or
one inside a `py:` stage's base64, which has none) stays fused into its
enclosing word token. Group tokens into stages by splitting on each
bare `"|"` token. `shlex` itself raises `ValueError` for unbalanced
quoting, which is exactly the "validated before any stage runs" parse
-time-error requirement in Sec. 6 -- no separate check needed.

An empty pipeline (no tokens at all) is a `ValueError` ("empty
pipeline"), and an empty stage (two adjacent `|`s, or a leading/trailing
`|`) is a `ValueError` naming its stage position -- both structural,
both validated upfront.

### 2. Classifying and validating each stage upfront

For each token group:

- **Exactly one token, starting with the literal `py:` prefix** -> a
  `py` stage. Decode the base64 immediately
  (`base64.b64decode(token[3:].encode("ascii"),
  validate=True).decode("utf-8")`, the same call/exception handling
  convention `desk_proc.py`/`jobs.py`/`custom_widgets.py` already use)
  -- `binascii.Error`/`UnicodeDecodeError` here becomes the upfront
  `ValueError` Sec. 6 calls for ("a malformed `py:` prefix (bad
  base64)"). The *decoded* Python source is stored on the parsed stage;
  it is not evaluated until that stage actually runs (evaluating it is
  a runtime concern, per Sec. 6 -- only the base64 well-formedness is
  structural).
- **Otherwise** -> a `verb` stage. The first token is the verb name;
  it must be a key in the registry passed to `run_pipeline` (default
  `VERB_REGISTRY`), else an upfront `ValueError` ("unknown verb
  '<name>'") -- Sec. 6's "an unknown verb name" case. The remaining
  tokens are that stage's raw string arguments, already shlex-split by
  the single tokenization pass above (this subsumes Sec. 2's own
  "split each verb stage's text after the verb name with
  `shlex.split`" -- doing it as one pass rather than two is equivalent
  for posix-mode shlex and avoids re-deriving each stage's substring
  from the token list just to re-split it).

This produces a list of fully-validated, parsed stages before any
execution begins.

### 3. Running a verb stage (`pipeline_dsl._run_verb_stage`)

- `inspect.signature(fn).parameters` gives the verb's declared
  parameters; skip the first (the piped-value parameter, per Sec. 3 --
  always present, even if named `_` and unused).
- For each raw string argument, coerce it against the corresponding
  remaining parameter's annotation (positionally; an argument past the
  last declared parameter is passed through as a raw string and left
  for the eventual `TypeError` to catch, per Sec. 2's "wrong argument
  count ... is also a per-stage runtime failure, not validated ahead of
  time"):
  - `int`/`float` annotation -> `int(x)`/`float(x)`.
  - `bool` annotation -> case-insensitive `{"true": True, "false":
    False}` lookup; anything else raises `ValueError` (never Python's
    own truthy-any-nonempty-string `bool(x)`, per Sec. 2's explicit
    call-out).
  - No annotation, or annotated `str` -> the raw string, unchanged.
- Call `fn(piped_value, *coerced_args)`. A coercion failure, a wrong
  -arity `TypeError`, or any exception the verb's own body raises is
  caught by the shared per-stage `try/except` in `run_pipeline` (Sec.
  6), not handled specially here.

### 4. Running a `py` stage (`pipeline_dsl._run_py_stage`)

`eval(decoded_source, {})` -- an empty globals dict still gets a real
`__builtins__` inserted automatically by `eval` itself, giving exactly
the "builtins only, no injected Desk object" namespace Sec. 5 calls
for, with no extra ceremony. If the result is `callable`, call it with
the piped value and use *that* return value as the stage's output
(Sec. 5's "function" case); otherwise use the evaluated value directly
(the "expression" case). A `SyntaxError`/`NameError`/anything else
`eval` or the call raises is a per-stage runtime failure, same as a
verb stage -- per Sec. 6, only the base64 decode step is checked
upfront, not the Python content itself.

### 5. `run_pipeline(text, registry=VERB_REGISTRY) -> dict`

1. Tokenize and validate every stage upfront (steps 1-2 above); a
   structural problem raises `ValueError` immediately, propagating to
   the caller uncaught (Sec. 6: "raises immediately", not captured in
   the result dict -- there is no partial pipeline to report on yet).
2. Walk the validated stages in order, fail-fast: run each one inside a
   `try/except Exception`, building its entry in `stages` per Sec. 6's
   exact shape (`stage`, `kind`, `verb`, `args`, `ok`, `output`,
   `error`). After a stage completes successfully, also check the
   "ok"-dict failure signal (`isinstance(output, dict) and
   output.get("ok") is False`) and treat it as that stage's own
   failure (`error = "verb reported ok: false"`, no traceback) per Sec.
   4/Sec. 6. Stop at the first failing stage either way.
3. Return the top-level `{"ok", "stages", "value", "traceback"}` dict
   exactly as Sec. 6 specifies -- `traceback.format_exc()` only when
   the failing stage actually raised.

### 6. The verb registry (`pipeline_dsl.VERB_REGISTRY`)

All five backed for real, matching Sec. 4's illustrative catalog
verb-for-verb:

- `reveal_widget(_, instance_id: str) -> {"ok": bool}` and
  `screenshot_widget(_, instance_id: str, path: str) -> {"ok": bool,
  "path": str}` and `screenshot_desk(_, path: str) -> {"ok": bool,
  "path": str}` and `list_widget_instances(_) -> list[dict]` all route
  through `current_context.get_main_window()`/`get_gui_thread_caller()`
  the same way `DeskProcApi` and `desk_mcp_server.py`'s own existing
  tool handlers already do (`window.zoom_to_widget_by_instance_id`/
  `screenshot_widget_instance`/`screenshot_desk`/`get_state_dict()`), a
  third, deliberate duplication of that same thin wrapper -- consistent
  with `desk_mcp_server.py`'s own top-of-file rationale for why it
  duplicates `DeskProcApi` rather than importing it (a widget's
  `widget.py` isn't meant to be imported from outside its directory,
  and neither the MCP server nor this new module is that widget).
  Raises `RuntimeError` (caught as a normal per-stage runtime failure)
  if no window/GUI-thread caller is registered yet, instead of
  returning a silently-empty/False result -- callers can tell "Desk
  isn't ready" apart from "the widget wasn't found".
- `open_image(piped: dict) -> {"ok": bool}` -- reads `piped["path"]`
  (`TypeError`/`KeyError` if `piped` isn't a dict with that key, a
  normal runtime failure) and writes a fresh `OpenImage <path>` tempui
  file into the current Desk's `.desk_temp/` directory (a random
  `uuid.uuid4().hex` filename -- content-based `detect_temp_ui_kind`
  means the exact name doesn't matter), the same mechanism a dropped
  image file or a hand-authored `OpenImage` tempui file already
  triggers, per `tempui-image.md`. Fire-and-forget, like every other
  `OpenImage` file: `{"ok": True}` once the file is written; `{"ok":
  False}` if there's no current Desk directory known or its
  `.desk_temp/` doesn't exist yet, or if writing fails. This is the
  one verb with no pre-existing synchronous "do the thing and get a
  real result back" primitive to call (unlike the other four, which
  already have one via `DeskWindow`) -- writing the tempui file is the
  existing, documented, already-safe way to trigger this action from
  outside the GUI thread, so it's reused as-is rather than inventing a
  new privileged direct-placement method for this one verb.

### 7. Transport: `desk_run_pipeline` MCP tool

A new `@tool("desk_run_pipeline", ..., {"pipeline": str})` in
`desk_mcp_server.py`, next to the other `desk_*` tools. Its handler
calls `pipeline_dsl.run_pipeline(args["pipeline"])` directly (no GUI
-thread marshaling at the tool-handler level -- `run_pipeline` isn't a
blocking Qt call itself, only the individual verbs it may invoke are,
and they marshal internally) inside a `try/except ValueError` (a
structural parse error, per Sec. 6, becomes `_text_result(str(e),
is_error=True)`) and returns `_text_result(json.dumps(result))` on
success, following every other tool's `_text_result`/`is_error`
convention in this file.

## Key design decisions / tradeoffs

- **Single-pass tokenization** (Sec. 2 above) instead of the design
  plan's literal two-pass description (split into stages, then
  `shlex.split` each stage's own substring) -- behaviorally identical
  for posix-mode `shlex`, simpler to implement and to keep the "`py:`
  stages are recognized before general verb-stage parsing" rule
  obviously true (the whole token *is* the stage when it's a single
  token starting with `py:`).
- **All five illustrative-catalog verbs get real backing**, not just
  a couple with the rest stubbed -- four of the five (`reveal_widget`/
  `screenshot_widget`/`screenshot_desk`/`list_widget_instances`)
  already have an exact, safe, synchronous `DeskWindow` method to call
  (the same ones `DeskProcApi`/`desk_mcp_server.py` already wrap), so
  there's no real cost to wiring them for real rather than leaving
  `NotImplementedError` placeholders. `open_image` has no such existing
  synchronous primitive, so it reuses the existing asynchronous
  tempui-file mechanism instead of adding a new one -- see point 6
  above. This isn't new scope beyond the design plan: the catalog was
  already fully specified, just marked "non-binding" about *which*
  verbs exist first, not that they shouldn't be built.
- **Transport is the MCP server, not a `Job`/`DeskProc` `Script` line**
  -- a pipeline is a single string an agent already has in hand
  mid-conversation (unlike a whole Python script), so a direct tool
  call avoids the file-drop-and-click-Start ceremony entirely for what
  is meant to be a lightweight, frequent operation. This doesn't
  preclude a `Job`/`DeskProc` transport later; per the design plan's
  own framing, the language is unaffected by which transport(s) exist.
- **No new tempui-DSL keyword or doc file** -- the pipeline DSL isn't
  itself a dropped-file kind, so it gets no `tempui-*.md` file; the new
  MCP tool documents itself via its own `@tool(...)` description string
  (the same discoverability every other `desk_*` tool already relies
  on), plus the one changelog entry noted above.

## Verification

`tests/verify/verify_pipeline_dsl.py`, no browser needed (in-process
Python + a `_FakeWindow`, matching `verify_desk_mcp_server.py`'s
existing shape under `QT_QPA_PLATFORM=offscreen`):

- Stage splitting: a quoted `|` inside an argument stays one stage
  (design plan's own `reveal_widget 'a | b'` example); an unquoted `|`
  splits; a `py:` stage's base64 (including one with `+`/`/` bytes)
  survives tokenization as a single token; unbalanced quoting raises
  `ValueError`; an empty pipeline and an empty stage (`foo | | bar`)
  both raise `ValueError`.
- Verb-stage argument coercion: `int`/`float`/`bool` (`true`/`false`,
  case-insensitively; a non-`true`/`false` value raises) parameters
  coerce correctly; an unannotated/`str` parameter passes the raw
  string through unchanged; an unknown verb name raises `ValueError`
  upfront (before any stage runs -- assert via a registered fake verb
  that a *later* stage's side effect never happens when an *earlier*
  stage's name is bad, since validation is upfront for the whole
  pipeline).
- The `py:` escape hatch: an expression-only stage (e.g. `py:` of
  `"1 + 1"`) returns its value directly and ignores the piped value;
  a callable result (a `lambda`) is invoked with the piped value; a
  malformed base64 `py:` token raises `ValueError` upfront; a decoded
  -but-invalid-Python `py:` stage (e.g. `"1 +"`) is a per-stage runtime
  failure (`SyntaxError` in `error`, not raised to the caller).
  the design plan's own worked example 2
  (`list_widget_instances | py:<...filter lambda...>`) run end-to-end
  against a fake window with several instances, confirming only the
  matching ones survive.
- Fail-fast + the result contract: the design plan's own worked
  example 3 (a `reveal_widget` on a nonexistent instance, i.e. an
  "ok": False-returning stage, followed by a `screenshot_widget` that
  must never run) reproduced exactly, checking the returned dict
  against the plan's own spelled-out expected result.
- The full happy-path pipeline: the design plan's own worked example 1
  (`reveal_widget abc123 | screenshot_widget abc123 shots/x.png |
  open_image`) against a fake window and a fake current-Desk directory,
  confirming the final `open_image` stage really wrote an `OpenImage`
  tempui file into `.desk_temp/` naming the screenshot's own path.
- Each of the five built-in verbs individually against a `_FakeWindow`/
  registered `current_context`, including the "not ready" (no window,
  no GUI-thread caller) case raising cleanly rather than crashing.

`tests/verify/verify_desk_mcp_server.py` gets a new
`test_run_pipeline_*` group: a successful pipeline returns the parsed
JSON result contract; a structural error (unknown verb) comes back as
`is_error: True` with the raw message, not a stack trace.

Full `tests/verify/` regression suite run afterward to confirm nothing
else regressed.
