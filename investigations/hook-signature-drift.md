# Why `get_centered_widget_opener`'s documented shape and real shape disagreed

Pre-investigation for the fix to
`../FEEDBACK/FEEDBACK-DESK-claude-desk-markdown-view-button-crashes-opener-arg-mismatch-2026-10-09-1420.md`
(Markdown View / `[image]` link crash: `opener("markdown", path)` puts the
`Path` into `size`). The question asked: how did documentation,
implementation and tests come to disagree, and do we need a mechanical check
(a "pre-commit" check) that new/changed code matches its docs and the mocks
in tests?

## Timeline

1. **Before TODO `83427f4`** (2026-09-22): the hook was
   `Callable[[str], QWidget | None]`; the real
   `open_widget_content_centered(widget_id, size=None, instance_id=None)`.
   The alias was already a lossy hand-copy (it hid `size` and `instance_id`),
   but nothing depended on the difference.
2. **`83427f4`** (`a5ba5d4`) added file association. In the *same commit*:
   - the implementation **appended** `path` as the 4th parameter (the natural
     edit to a method that already had optional params);
   - `current_context.py`'s alias became `Callable[[str, Path | None], ...]`
     and the docstring said "`path` ... second positional arg".
   The two halves disagree within one commit. The author wrote the doc as
   the "ideal" shape rather than reading it back off the code.
3. **Every consumer touched by that commit passed `path=` by keyword**:
   `project_files._open_in_widget` (`opener(widget_id, path=path)`), and the
   tests that call the real method (`verify_file_explorer_fallback_chain`,
   `verify_html_widget_opened_file`, both `path=`). A keyword call works
   against both the documented and the real shape, so **no check in that
   commit could observe the disagreement.**
4. **TODOs `10b4d7d` / `6ff3be8`** (2026-10-03, a different change, later
   session) added the Claude (Desk) callers. They had no reason to open
   `window.py`; they read the documented alias, wrote
   `opener("markdown", path)` / `opener("image_viewer", path)`, and wrote
   tests with `lambda wid, path: opened.append(...)` -- a fake that copies the
   alias. Caller and fake were both faithful to the *doc*; the doc was the
   thing that was wrong. Neither plan has a step like "read the bound
   function".
5. Nothing connected the two until a human clicked the button.

## Root causes (in order of weight)

1. **The contract is written twice, by hand, in places nothing compares.**
   `current_context.py` has ~30 `Callable[...]` aliases, each a hand copy of
   a `DeskWindow` method signature. Python does not check them. The alias is
   also expressively weak: `Callable` can't state parameter names, keyword-only
   status or defaults, so "second positional" lived in prose.
2. **Test fakes copy the alias, not the function.** About 25 verify scripts /
   ~78 call sites register hand-written fakes (`lambda wid, path: ...`). A
   fake validates the caller against the doc, so a wrong doc is a *shared*
   blind spot: caller, fake and doc all agree, the real function alone differs.
   (Contrast `verify_viewer_widgets_edit_button`'s `_FakeWindow`, which
   re-declares the real signature -- also a copy, but a prose-comment-tracked
   one.)
3. **The one commit that could have caught it only used keyword calls**, and
   the process (`development-process.md`) has no rule that a change to a
   documented hook shape must be exercised positionally *through the real
   method*.
4. **A static type checker would have caught it, but none is in use.**
   `set_centered_widget_opener(self.open_widget_content_centered)` passes a
   method whose 2nd parameter is `tuple[int,int] | None` where
   `Path | None` is declared -- a plain type error (the feedback is right that
   checkers ignore parameter *names*, but here the *types* differ). No
   mypy/pyright/ruff is installed in `.venv`, and `CLAUDE.md` says to avoid
   adding dependencies.

## Audit: is this the only drift?

Compared every `current_context.set_X(self.method)` binding in `window.py`
with its alias (script: arity + order of parameters). Result: **all the
other ~25 hooks agree** on positional arity and order. The two divergences:

- `centered_widget_opener`: the bug above.
- `widget_opener`: alias `[str]`, real `(widget_id, pos, size, instance_id,
  path)`. Not wrong for the positional-1 callers, but it hides `path=` which
  `open_widget_content` also supports; same class of weak alias.

(`popup_opener`, `event_mediator`, `hot_reload_broker`, `hmsvc_manager` bind
differently and weren't in the automated comparison; the popup service's
`show_blocking` is covered by its own tests.) So this is one real bug from a
structural weakness, not a pattern of existing bugs.

## Do we need a pre-commit check?

There is no git hook infrastructure in this repo; the gate is the
`tests/verify` suite plus the process doc. So "pre-commit" realistically means
"a verify script in the suite" plus a process rule. Options considered:

| Option | Catches this? | Cost | Verdict |
| --- | --- | --- | --- |
| mypy/pyright | yes (types differ) | new dependency, large untyped baseline noise | no (CLAUDE.md) |
| **Bespoke verify script** comparing each hook alias to the real bound method with `inspect` (arity, order, annotation per position, and that required params of the method are satisfiable by the alias) | yes | small; no dependency; runs in the suite | **do** |
| Single-source the contract: a `Protocol` with `__call__(widget_id, *, size=None, instance_id=None, path=None)` for hooks that take optional params, and the verify script compares `inspect.signature` of the real method to the Protocol's `__call__` exactly | yes, and prevents the *prose-only* contract | moderate; limited to the 2 opener hooks | **do for the openers** |
| Make the setters validate the registered callable at registration time | yes, also for fakes | would break existing legit fakes (e.g. `lambda wid:` registered for the centered hook); noisy | no |
| Rule that fakes of a hook be built from the real method (`DeskWindow.method` bound to a stand-in) where the shape matters | partly | tests rewritten piecemeal | adopt as guidance, don't mass-rewrite |
| Git pre-commit hook running changed-file checks | n/a | new infra; the suite is already the gate | defer |

Recommendation: the signature-conformance verify script is the mechanical
check; it targets the actual failure (alias vs real) and costs almost
nothing. A broader "docs must match code" gate isn't feasible mechanically
beyond signatures; for prose docs the existing process (plans, tempui doc
review) stays the control.

## Decisions to carry into the TODO(s)

- Fix the signature: `path` second after `widget_id`, `size`/`instance_id`
  keyword-only (`*`), matching the documented contract and both Claude (Desk)
  callers. Audit all callers (`project_files` already uses `path=`;
  `verify_viewer_widgets_edit_button`'s fake and `verify_hmsvc_dir_watcher`'s
  lambda mirror the old shape).
- `current_context.py`: a Protocol (or equivalent single-sourced signature)
  for the two opener hooks, and a module docstring note that the other
  `Callable` aliases are unchecked documentation verified only by the new
  conformance script.
- New `tests/verify/verify_current_context_hook_signatures.py`: compares
  every `set_X(self.method)` binding against its alias; plus a test that
  calls the real `DeskWindow.open_widget_content_centered` positionally the
  way the Claude (Desk) widget does and asserts `path` reaches
  `set_file` / `getOpenedFile`.
- Repair the Claude (Desk) tests to drive the real bound method (via the
  existing `_FakeWindow` pattern), not a lambda copy of the alias.
- `development-process.md`: a short rule -- when you change a hook's shape,
  change the Protocol/alias, the real method and the conformance script
  together, and call it positionally through the real method at least once.
